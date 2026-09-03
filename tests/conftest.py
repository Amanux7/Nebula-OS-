from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from agent_company_os.adapters.clocks import FakeClock
from agent_company_os.adapters.ids import DeterministicIdGenerator
from agent_company_os.adapters.in_memory import InMemoryDomainStore
from agent_company_os.application.service import DomainService


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 8, 29, 9, 0, tzinfo=UTC))


@pytest.fixture
def store() -> InMemoryDomainStore:
    return InMemoryDomainStore()


@pytest.fixture
def service(store: InMemoryDomainStore, clock: FakeClock) -> DomainService:
    return DomainService(store, clock, DeterministicIdGenerator())


@pytest.fixture
def tick(clock: FakeClock) -> Callable[[], None]:
    def advance() -> None:
        clock.advance(timedelta(seconds=1))

    return advance
