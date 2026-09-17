"""Connector recovery is evidence lookup, not a second execution path."""

from typing import Protocol

from agent_company_os.domain.recovery import ConnectorCapabilities, RemoteLookup


class RecoveryConnector(Protocol):
    @property
    def capabilities(self) -> ConnectorCapabilities: ...
    async def lookup_status(self, idempotency_key: str) -> RemoteLookup: ...
