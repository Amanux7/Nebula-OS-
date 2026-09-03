"""Scripted adapter: deterministic runtime test double, not an AI model."""

from collections.abc import Callable

from agent_company_os.domain.decisions import ModelFailure
from agent_company_os.ports.model import AgentModelRequest


class FakeModel:
    model_name = "scripted-v1"

    def __init__(
        self,
        responses: tuple[str | Exception, ...],
        on_invoke: Callable[[AgentModelRequest], None] | None = None,
    ) -> None:
        self._responses = responses
        self.requests: list[AgentModelRequest] = []
        self._on_invoke = on_invoke

    async def invoke(self, request: AgentModelRequest) -> str:
        index = len(self.requests)
        self.requests.append(request)
        if self._on_invoke:
            self._on_invoke(request)
        if index >= len(self._responses):
            raise ModelFailure("provider_unavailable")
        response = self._responses[index]
        if isinstance(response, Exception):
            raise response
        return response
