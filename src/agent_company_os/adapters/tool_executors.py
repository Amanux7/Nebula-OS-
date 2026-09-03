"""Two bounded fixture lookups and a failure-injectable scripted executor."""

import asyncio
import json
from collections.abc import Callable, Mapping

from agent_company_os.domain.agent import Fact
from agent_company_os.domain.tools import (
    CompanyLookupInput,
    SourceLookupInput,
    ToolError,
    ToolFailure,
    ToolInput,
    ToolInvocation,
    ToolOutput,
)


def output_json(output: ToolOutput) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "subject": output.subject,
            "facts": [
                {"key": fact.key, "value": fact.value, "source_id": fact.source_id}
                for fact in output.facts
            ],
            "notes": output.notes,
        }
    )


class CompanyFactLookup:
    def __init__(self, companies: Mapping[str, tuple[Fact, ...]]) -> None:
        self._companies = {key: tuple(facts) for key, facts in companies.items()}

    async def execute(self, request: ToolInput, context: ToolInvocation) -> str:
        if not isinstance(request, CompanyLookupInput):
            raise ToolFailure(ToolError.VALIDATION_ERROR)
        if request.company_name not in self._companies:
            raise ToolFailure(ToolError.NOT_FOUND)
        return output_json(ToolOutput(request.company_name, self._companies[request.company_name]))


class SourceFactLookup:
    def __init__(self, facts: tuple[Fact, ...]) -> None:
        self._facts = tuple(facts)

    async def execute(self, request: ToolInput, context: ToolInvocation) -> str:
        if not isinstance(request, SourceLookupInput):
            raise ToolFailure(ToolError.VALIDATION_ERROR)
        return output_json(
            ToolOutput(
                request.source_id,
                tuple(
                    fact
                    for fact in self._facts
                    if fact.source_id == request.source_id and fact.key in request.keys
                ),
            )
        )


class FakeToolExecutor:
    def __init__(
        self,
        results: tuple[str | Exception, ...],
        *,
        gate: asyncio.Event | None = None,
        entered: asyncio.Event | None = None,
        on_execute: Callable[[ToolInvocation], None] | None = None,
    ) -> None:
        self.results = results
        self.requests: list[ToolInput] = []
        self.invocations: list[ToolInvocation] = []
        self.gate = gate
        self.entered = entered
        self.on_execute = on_execute

    async def execute(self, request: ToolInput, context: ToolInvocation) -> str:
        index = len(self.requests)
        self.requests.append(request)
        self.invocations.append(context)
        if self.entered is not None:
            self.entered.set()
        if self.on_execute is not None:
            self.on_execute(context)
        if self.gate is not None:
            await self.gate.wait()
        if index >= len(self.results):
            raise ToolFailure(ToolError.UPSTREAM_UNAVAILABLE)
        result = self.results[index]
        if isinstance(result, Exception):
            raise result
        return result
