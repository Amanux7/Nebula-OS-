"""Deterministic and scripted offline planning strategies."""

from collections import deque

from agent_company_os.domain.orchestration import (
    AgentRequirements,
    OrchestrationRequest,
    PlannedTask,
    PlanProposal,
)


class ResearchBriefPlanStrategy:
    strategy_id = "research-brief-linear"
    strategy_version = "1"

    async def plan(self, request: OrchestrationRequest) -> PlanProposal:
        return PlanProposal(
            request.workspace_id,
            request.goal_id,
            (
                PlannedTask(
                    "research",
                    "Collect approved competitor facts",
                    ("Produce grounded research facts",),
                    requirements=AgentRequirements(("research",)),
                    priority=10,
                ),
                PlannedTask(
                    "analysis",
                    "Analyze competitor differences",
                    ("Produce grounded comparative analysis",),
                    ("research",),
                    AgentRequirements(("analysis",)),
                    20,
                ),
                PlannedTask(
                    "brief",
                    "Prepare competitor brief",
                    ("Produce a grounded final brief",),
                    ("analysis",),
                    AgentRequirements(("writing",)),
                    30,
                ),
            ),
        )


class FakeOrchestrationStrategy:
    strategy_id = "fake-planner"
    strategy_version = "1"

    def __init__(self, responses: tuple[PlanProposal | Exception, ...]) -> None:
        self._responses = deque(responses)
        self.requests: list[OrchestrationRequest] = []

    async def plan(self, request: OrchestrationRequest) -> PlanProposal:
        self.requests.append(request)
        response = self._responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response
