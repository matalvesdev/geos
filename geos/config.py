"""GEOS configuration (SPEC-001): geos.yaml loading with defaults and strict top-level keys."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised for invalid or unreadable configuration."""


_TOP_LEVEL_KEYS = {
    "company",
    "storage",
    "knowledge",
    "models",
    "agents",
    "automations",
    "approvals",
    "features",
    "workflows",
    "repositories",
}


@dataclass
class Settings:
    """Loaded GEOS configuration. Secret-free by construction."""

    root: str = "."
    company_name: str = "Example"
    storage_provider: str = "sqlite"
    storage_mode: str = "isolated"
    storage_path: str = ".geos/geos.db"
    knowledge_rag: bool = True
    knowledge_graph: bool = True
    knowledge_embeddings: dict[str, Any] = field(default_factory=dict)
    models: dict[str, Any] = field(default_factory=dict)
    agents: dict[str, Any] = field(default_factory=dict)
    automations: dict[str, Any] = field(default_factory=dict)
    approvals: dict[str, str] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    workflows_dir: str = "workflows"
    repositories: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def defaults(cls, root: str = ".") -> "Settings":
        return cls(root=root)

    @property
    def db_path(self) -> Path:
        p = Path(self.storage_path)
        if p.is_absolute():
            return p
        return Path(self.root) / p

    @classmethod
    def from_path(cls, path: str | Path, root: str | Path = ".") -> "Settings":
        path = Path(path)
        if not path.exists():
            return cls.defaults(root=str(root))
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"{path} must contain a YAML mapping at the top level")
        unknown = set(raw) - _TOP_LEVEL_KEYS
        if unknown:
            raise ConfigError(f"Unknown config key(s) {sorted(unknown)} in {path}")

        settings = cls.defaults(root=str(root))
        company = raw.get("company") or {}
        if isinstance(company, dict):
            settings.company_name = str(company.get("name") or settings.company_name)

        storage = raw.get("storage") or {}
        if isinstance(storage, dict):
            settings.storage_provider = str(storage.get("provider") or settings.storage_provider)
            settings.storage_mode = str(storage.get("mode") or settings.storage_mode)
            settings.storage_path = str(storage.get("path") or settings.storage_path)

        knowledge = raw.get("knowledge") or {}
        if isinstance(knowledge, dict):
            settings.knowledge_rag = bool(knowledge.get("rag", settings.knowledge_rag))
            settings.knowledge_graph = bool(knowledge.get("graph", settings.knowledge_graph))
            settings.knowledge_embeddings = dict(knowledge.get("embeddings") or {})

        settings.models = dict(raw.get("models") or {})
        settings.agents = dict(raw.get("agents") or {})
        settings.automations = dict(raw.get("automations") or {})
        settings.approvals = {str(k): str(v) for k, v in (raw.get("approvals") or {}).items()}
        settings.features = dict(raw.get("features") or {})

        workflows = raw.get("workflows") or {}
        if isinstance(workflows, dict):
            settings.workflows_dir = str(workflows.get("dir") or settings.workflows_dir)

        repos = raw.get("repositories") or []
        if isinstance(repos, list):
            settings.repositories = [dict(r) for r in repos if isinstance(r, dict)]
        return settings

    def feature(self, name: str) -> bool:
        """Feature flag lookup (SPEC-110). Missing flags default to False (opt-in)."""
        value = self.features.get(name)
        if isinstance(value, bool):
            return value
        if isinstance(value, dict):
            return bool(value.get("enabled", False))
        return False
