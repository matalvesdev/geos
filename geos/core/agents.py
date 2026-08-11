"""Agent abstraction (spec §38–§42). Primitives now; declarative YAML agents later.

No god agent: the catalog below is the planned specialized set (spec §40). Collaboration
always requires goal/input/expected_output/budget/max_steps/timeout/exit_condition (§42).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Agent:
    """Declarative agent definition (subset of §38)."""

    id: str
    role: str
    tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    approval: dict[str, str] = field(default_factory=dict)  # action -> risk level

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("agent id is required")


# Planned specialized agents (spec §40) — declared, not yet implemented.
PLANNED_AGENTS: list[str] = [
    "ChiefGrowthAgent", "ResearchAgent", "CompetitorAgent", "TrendAgent", "SEOAgent",
    "ContentStrategistAgent", "WriterAgent", "EditorAgent", "FactCheckAgent", "BrandAgent",
    "CreativeAgent", "SocialAgent", "InstagramAgent", "BlogAgent", "NewsletterAgent",
    "CampaignAgent", "GrowthAgent", "ExperimentAgent", "AnalyticsAgent", "EducationAgent",
    "AcademyAgent", "CommunityAgent", "DevRelAgent", "LeadIntelligenceAgent",
    "QualificationAgent", "LeadRouterAgent", "NurtureAgent", "SalesAgent", "MeetingAgent",
    "CRMManagerAgent", "DocumentationAgent", "KnowledgeAgent",
]


class AgentRegistry:
    """Holds declared agents (register future implementations here)."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.id in self._agents:
            raise ValueError(f"duplicate agent id {agent.id!r}")
        self._agents[agent.id] = agent

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def list(self) -> list[Agent]:
        return list(self._agents.values())
