"""SEO engine (SPEC-023): deterministic audit over what GEOS knows.

Documents (markdown ingerido), content objects e knowledge graph — sem crawl web e
sem dados de tráfego: nunca fabrica sinais. Cada run grava um snapshot persistido
(seo_audits + seo_issues) para histórico e comparação.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..storage.database import Database
from ..storage.repos import RepoFactory

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# Explicit accented range (excludes ×÷) — word counts stay accurate.
_WORD_RE = re.compile(r"[A-Za-z0-9À-ÖØ-öø-ÿ]+")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_MIN_WORDS_THIN = 40
_DECAY_DAYS = 90  # local heuristic: age with no update → refresh signal
_DOC_SUFFIXES = (".md", ".markdown", ".txt")


@dataclass
class SeoIssue:
    severity: str  # critical | warning | info
    category: str
    target: str | None
    title: str
    detail: str | None = None
    recommendation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "category": self.category,
                "target": self.target, "title": self.title, "detail": self.detail,
                "recommendation": self.recommendation}


class SeoEngine:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = RepoFactory(db)
        self._knowledge = self._repo.knowledge
        self._content = self._repo.content

    # ---- audit: documents --------------------------------------------------
    def audit_docs(self) -> list[SeoIssue]:
        docs = self._knowledge.list_documents(limit=5000)
        if not docs:
            return [SeoIssue(
                "info", "coverage", None,
                "Nenhum documento ingerido",
                "Rode `geos knowledge ingest <dir>` antes de auditar.",
                "geos knowledge ingest docs --source site")]
        uri_set = {self._normalize_uri(d["uri"]) for d in docs}
        issues: list[SeoIssue] = []
        referenced: set[str] = set()

        for doc in docs:
            chunks = self._knowledge.chunks_for_document(doc["id"])
            text = " ".join(str(c.get("content") or "") for c in chunks)
            links = self._links_in(doc["uri"], text)
            doc_uri_norm = self._normalize_uri(doc["uri"])
            for link in links:
                if self._normalize_uri(link) != doc_uri_norm:
                    referenced.add(self._normalize_uri(link))  # no self-references
            broken = [l for l in links if self._normalize_uri(l) not in uri_set]
            for target in broken:
                issues.append(SeoIssue(
                    "critical", "broken_link", doc["uri"],
                    f"Link quebrado para {target!r}",
                    f"Em {doc['uri']} o link interno não resolve para nenhum documento ingerido.",
                    "Criar o documento alvo ou corrigir o caminho do link."))
            word_count = len(_WORD_RE.findall(text))
            if word_count < _MIN_WORDS_THIN:
                issues.append(SeoIssue(
                    "warning", "thin_content", doc["uri"],
                    f"Conteúdo fino ({word_count} palavras)",
                    f"Menos de {_MIN_WORDS_THIN} palavras — provavelmente sem profundidade.",
                    "Expandir com seções de processo, evidência e exemplos."))
            if not (doc.get("title") or "").strip():
                issues.append(SeoIssue(
                    "info", "metadata", doc["uri"],
                    "Documento sem título",
                    "Sem `title` persistido — use headings no início do arquivo.",
                    "Adicionar um título (H1) na primeira linha."))
            first_chunk = chunks[0].get("content", "") if chunks else ""
            if first_chunk.strip() and not first_chunk.lstrip().startswith("#"):
                issues.append(SeoIssue(
                    "info", "metadata", doc["uri"],
                    "Primeira linha sem heading",
                    "O documento começa sem H1 — o título da página fica indefinido.",
                    "Iniciar o arquivo com `# Título`."))
            if not links:
                issues.append(SeoIssue(
                    "info", "internal_linking", doc["uri"],
                    "Sem links internos de saída",
                    "Nenhum link `[text](path)` para outros documentos.",
                    "Adicionar links para documentos relacionados (pilar/cluster)."))

        for doc in docs:
            if self._normalize_uri(doc["uri"]) not in referenced:
                issues.append(SeoIssue(
                    "warning", "orphan", doc["uri"],
                    "Documento órfão (nenhum link interno aponta para ele)",
                    "Sem caminho de entrada a partir de outros documentos.",
                    "Referenciar este documento a partir de um pilar ou índice."))
        return issues

    # ---- audit: content ----------------------------------------------------
    def audit_content(self) -> list[SeoIssue]:
        issues: list[SeoIssue] = []
        items = self._content.list(limit=2000)
        topics_with_content = {
            str(i.get("topic") or "").strip().lower()
            for i in items if (i.get("topic") or "").strip()
        }
        if not items:
            issues.append(SeoIssue(
                "info", "coverage", None,
                "Nenhum objeto de conteúdo",
                "A tabela `content` está vazia (use `geos content create`).",
                "geos content create \"<tópico>\""))

        # gaps: TOPIC nodes from the graph without a content item (computed
        # even when the content table is empty — the gaps are the finding)
        for node in self._knowledge.list_nodes(node_type="TOPIC", limit=500):
            name = str(node.get("name") or "").strip()
            if not name or len(name) < 3:
                continue
            if name.lower() not in topics_with_content:
                issues.append(SeoIssue(
                    "info", "content_gap", f"TOPIC:{name}",
                    f"Tópico sem conteúdo: {name!r}",
                    "O knowledge graph conhece o tópico, mas não há objeto de conteúdo.",
                    f"geos content create \"{name}\" --keywords \"{name}\""))

        # cannibalization: same topic targeted by multiple content items
        by_topic: dict[str, list[str]] = {}
        for item in items:
            topic = str(item.get("topic") or "").strip().lower()
            if not topic:
                continue
            by_topic.setdefault(topic, []).append(str(item.get("slug") or item["id"]))
        for topic, slugs in by_topic.items():
            if len(slugs) > 1:
                issues.append(SeoIssue(
                    "warning", "cannibalization", f"topic:{topic}",
                    f"Cannibalização de tópico: {len(slugs)} conteúdos",
                    "Múltiplos objetos de conteúdo disputam o mesmo tópico "
                    f"({', '.join(slugs[:5])}).",
                    "Consolidar em um pilar e direcionar os demais para clusters."))

        # decay: local heuristics (age, no update, thin) — honest, no traffic claims
        now = datetime.now().astimezone()
        for item in items:
            if item["status"] == "ARCHIVED":
                continue
            signals: list[str] = []
            created = self._parse_iso(item.get("created_at"))
            updated = self._parse_iso(item.get("updated_at"))
            if created and (now - created).days > _DECAY_DAYS:
                signals.append(f"criado há {(now - created).days} dias")
            if updated and created and updated == created:
                signals.append("nunca atualizado")
            body = str(item.get("body") or "")
            if body and len(_WORD_RE.findall(body)) < _MIN_WORDS_THIN:
                signals.append("corpo curto")
            if signals:
                issues.append(SeoIssue(
                    "warning", "decay", f"content:{item.get('slug')}",
                    f"Possível decay de conteúdo: {item['title']}",
                    "Sinais locais: " + "; ".join(signals) + ".",
                    "Propor refresh (SPEC §83) e confirmar com analytics externos "
                    "(heurística local — sem dados de tráfego)."))
        return issues

    # ---- runner ------------------------------------------------------------
    def run_audit(self, scopes: tuple[str, ...] = ("docs", "content")) -> dict[str, Any]:
        issues: list[SeoIssue] = []
        if "docs" in scopes:
            issues.extend(self.audit_docs())
        if "content" in scopes:
            issues.extend(self.audit_content())
        summary = {"scopes": list(scopes), "total": len(issues)}
        for issue in issues:
            summary[issue.severity] = summary.get(issue.severity, 0) + 1
            summary.setdefault(f"by_category:{issue.category}", 0)
            summary[f"by_category:{issue.category}"] += 1
        audit_id = self._repo.seo.create_audit("+".join(scopes), summary)
        for issue in issues:
            self._repo.seo.insert_issue(
                audit_id, issue.severity, issue.category, issue.target,
                issue.title, issue.detail, issue.recommendation,
            )
        return {"audit_id": audit_id, "summary": summary,
                "issues": [i.to_dict() for i in issues]}

    def list_issues(self, severity: str | None = None) -> list[dict[str, Any]]:
        return self._repo.seo.list_issues(severity=severity)

    def last_summary(self) -> dict[str, Any] | None:
        return self._repo.seo.last_audit_summary()

    # ---- helpers -----------------------------------------------------------
    def _links_in(self, uri: str, text: str) -> list[str]:
        """Internal link targets (markdown links), resolved against uri's directory.
        Fenced code blocks and inline code are stripped first so example links in
        docs do not become false broken-link findings (SPEC-023).
        """
        source, _, rel = uri.partition("://")
        base_dir = os.path.dirname(rel)
        clean = _CODE_FENCE_RE.sub(" ", text)
        clean = _INLINE_CODE_RE.sub(" ", clean)
        targets: list[str] = []
        for match in _LINK_RE.finditer(clean):
            raw = match.group(1).split("#", 1)[0].split("?", 1)[0].strip()
            if not raw or "://" in raw or raw.startswith(("mailto:", "tel:")):
                continue  # external
            if not raw.lower().endswith(_DOC_SUFFIXES):
                continue  # assets/non-docs not indexed — skip to avoid noise
            if raw.startswith("/"):
                resolved = self._normalize_uri(f"{source}://{raw.lstrip('/')}")
            else:
                resolved = self._normalize_uri(
                    f"{source}://{os.path.join(base_dir, raw)}"
                )
            targets.append(resolved)
        return sorted(set(targets))

    @staticmethod
    def _normalize_uri(uri: str) -> str:
        source, _, rel = uri.partition("://")
        return f"{source}://{os.path.normpath(rel)}"

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None
        if parsed.tzinfo is None:
            return parsed.astimezone()
        return parsed
