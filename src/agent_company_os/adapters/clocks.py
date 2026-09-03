"""Production and deterministic clock adapters."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agent_company_os.domain.validation import require_utc


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(slots=True)
class FakeClock:
    current: datetime

    def __post_init__(self) -> None:
        require_utc(self.current, "current")

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        if delta.total_seconds() < 0:
            raise ValueError("FakeClock cannot move backwards.")
        self.current += delta
