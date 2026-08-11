"""Policy engine (spec §46–§47, §153). Action risk classification with config override.

Risk classes: SAFE_AUTOMATIC · REVIEW_RECOMMENDED · HUMAN_APPROVAL_REQUIRED ·
PROHIBITED_AUTOMATION.
"""

from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    SAFE_AUTOMATIC = "SAFE_AUTOMATIC"
    REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    PROHIBITED_AUTOMATION = "PROHIBITED_AUTOMATION"


# Default policy (spec §47). Config `approvals:` overrides per action.
DEFAULT_POLICY: dict[str, RiskLevel] = {
    "research.run": RiskLevel.SAFE_AUTOMATIC,
    "report.generate": RiskLevel.SAFE_AUTOMATIC,
    "ideation.run": RiskLevel.SAFE_AUTOMATIC,
    "content.draft": RiskLevel.SAFE_AUTOMATIC,
    "seo.recommend": RiskLevel.SAFE_AUTOMATIC,
    "experiment.propose": RiskLevel.SAFE_AUTOMATIC,
    "blog.publish": RiskLevel.HUMAN_APPROVAL_REQUIRED,
    "social.publish": RiskLevel.HUMAN_APPROVAL_REQUIRED,
    "newsletter.send": RiskLevel.HUMAN_APPROVAL_REQUIRED,
    "meeting.invite": RiskLevel.HUMAN_APPROVAL_REQUIRED,
    "paid_media.run": RiskLevel.HUMAN_APPROVAL_REQUIRED,
    "resource.delete": RiskLevel.HUMAN_APPROVAL_REQUIRED,
    # Explicitly prohibited until architecture proves otherwise:
    "social.engage_automated": RiskLevel.PROHIBITED_AUTOMATION,
}

_RISK_BY_VALUE = {r.value: r for r in RiskLevel}


def classify_action(action: str, config_overrides: dict[str, str] | None = None) -> RiskLevel:
    """Classify an action. Config overrides win; unknown actions default to REVIEW_RECOMMENDED."""
    if config_overrides:
        override = config_overrides.get(action)
        if override is not None:
            parsed = _RISK_BY_VALUE.get(str(override).upper())
            if parsed is not None:
                return parsed
    return DEFAULT_POLICY.get(action, RiskLevel.REVIEW_RECOMMENDED)
