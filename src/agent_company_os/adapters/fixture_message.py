"""One offline write capability. No network, credentials, or production destinations."""

from agent_company_os.adapters.tool_executors import output_json
from agent_company_os.domain.tools import (
    FixtureMessageInput,
    ToolError,
    ToolFailure,
    ToolInput,
    ToolInvocation,
    ToolOutput,
)


class FixtureMessageExecutor:
    def __init__(self, *, reject: bool = False) -> None:
        self.deliveries: dict[str, FixtureMessageInput] = {}
        self.reject = reject

    async def execute(self, request: ToolInput, context: ToolInvocation) -> str:
        if not isinstance(request, FixtureMessageInput):
            raise ToolFailure(ToolError.VALIDATION_ERROR)
        if self.reject:
            raise ToolFailure(ToolError.REJECTED)
        key = str(context.id)
        if key in self.deliveries and self.deliveries[key] != request:
            raise ToolFailure(ToolError.VALIDATION_ERROR)
        self.deliveries[key] = request
        return output_json(ToolOutput(request.destination, (), "fixture_delivery_observed"))
