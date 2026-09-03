"""Provider-neutral, cooperative asynchronous model contract."""

from dataclasses import dataclass
from typing import Protocol

from agent_company_os.domain.agent import (
    ActionType,
    AgentDefinitionVersion,
    Observation,
    SuppliedContext,
)
from agent_company_os.domain.knowledge import EvidencePack
from agent_company_os.domain.tools import ToolVersion


@dataclass(frozen=True)
class AgentModelRequest:
    definition_version: AgentDefinitionVersion
    objective: str
    task: str
    acceptance_criteria: tuple[str, ...]
    constraints: tuple[str, ...]
    supplied_data: SuppliedContext
    observations: tuple[Observation, ...]
    allowed_actions: tuple[ActionType, ...]
    iteration: int
    max_iterations: int
    schema_version: int = 1
    available_tools: tuple[ToolVersion, ...] = ()
    knowledge_evidence: EvidencePack | None = None


class ModelPort(Protocol):
    @property
    def model_name(self) -> str: ...

    async def invoke(self, request: AgentModelRequest) -> str:
        """Return untrusted JSON; adapters must be nonblocking and honor cancellation."""
        ...
