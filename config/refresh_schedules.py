"""Issuance-aware refresh schedules for worker-free product refreshes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


UTC = timezone.utc
EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class IssuanceBoundary:
    hour: int
    minute: int = 0
    tz_name: str = "UTC"
    weekdays: tuple[int, ...] = tuple(range(7))

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)


@dataclass(frozen=True)
class IssuanceSchedule:
    boundaries: tuple[IssuanceBoundary, ...]
    grace_seconds: int = 20 * 60
    retry_seconds: int = 2 * 60

    def latest_boundary(self, now: datetime) -> datetime:
        now_utc = _aware_utc(now)
        candidates: list[datetime] = []
        for boundary in self.boundaries:
            local_now = now_utc.astimezone(boundary.timezone)
            for days_back in range(8):
                local_day = local_now.date() - timedelta(days=days_back)
                if local_day.weekday() not in boundary.weekdays:
                    continue
                local_candidate = datetime.combine(
                    local_day,
                    time(boundary.hour, boundary.minute),
                    boundary.timezone,
                )
                candidate = local_candidate.astimezone(UTC)
                if candidate <= now_utc:
                    candidates.append(candidate)
                    break
        if not candidates:
            raise ValueError("Issuance schedule has no usable boundary")
        return max(candidates)

    def refresh_due(
        self,
        *,
        now: datetime,
        source_issued_at: datetime | None,
        last_checked_at: datetime | None,
    ) -> bool:
        now_utc = _aware_utc(now)
        boundary = self.latest_boundary(now_utc)
        if source_issued_at is not None and _aware_utc(source_issued_at) >= boundary:
            return False
        if (
            last_checked_at is not None
            and now_utc - _aware_utc(last_checked_at)
            < timedelta(seconds=self.retry_seconds)
        ):
            return False
        if now_utc <= boundary + timedelta(seconds=self.grace_seconds):
            return True
        return (
            last_checked_at is None
            or _aware_utc(last_checked_at) < boundary
        )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc(*times: tuple[int, int]) -> tuple[IssuanceBoundary, ...]:
    return tuple(IssuanceBoundary(hour, minute) for hour, minute in times)


def _chicago(hour: int, minute: int = 0) -> IssuanceBoundary:
    return IssuanceBoundary(hour, minute, "America/Chicago")


SPC_OUTLOOK_SCHEDULES: dict[str, IssuanceSchedule] = {}

for hazard in ("cat", "torn", "wind", "hail", "cigtorn", "cigwind", "cighail"):
    SPC_OUTLOOK_SCHEDULES[f"1_{hazard}"] = IssuanceSchedule(
        _utc((1, 0), (6, 0), (13, 0), (16, 30), (20, 0))
    )
    SPC_OUTLOOK_SCHEDULES[f"2_{hazard}"] = IssuanceSchedule(
        (_chicago(1), *_utc((17, 30)))
    )
SPC_OUTLOOK_SCHEDULES["3_cat"] = IssuanceSchedule(
    (_chicago(2, 30), *_utc((19, 30)))
)
SPC_OUTLOOK_SCHEDULES["3_prob"] = SPC_OUTLOOK_SCHEDULES["3_cat"]
for day in range(4, 9):
    SPC_OUTLOOK_SCHEDULES[f"{day}_cat"] = IssuanceSchedule((_chicago(4),))

for hazard in ("windrh", "dryt"):
    SPC_OUTLOOK_SCHEDULES[f"fire_1_{hazard}"] = IssuanceSchedule(
        (_chicago(2), *_utc((17, 0)))
    )
    SPC_OUTLOOK_SCHEDULES[f"fire_2_{hazard}"] = IssuanceSchedule(
        (_chicago(2), *_utc((20, 0)))
    )
for day in range(3, 9):
    for hazard in ("drytcat", "drytprob", "windrhcat", "windrhprob"):
        SPC_OUTLOOK_SCHEDULES[f"fire_{day}_{hazard}"] = IssuanceSchedule(
            _utc((22, 0))
        )


TROPICAL_ROUTINE_SCHEDULE = IssuanceSchedule(
    _utc((3, 0), (9, 0), (15, 0), (21, 0))
)
TROPICAL_INTERMEDIATE_SCHEDULE = IssuanceSchedule(
    _utc((0, 0), (6, 0), (12, 0), (18, 0))
)
GTWO_SCHEDULE = IssuanceSchedule(_utc((0, 0), (6, 0), (12, 0), (18, 0)))


_WPC_SCHEDULES = {
    "ero_day1": IssuanceSchedule(_utc((3, 0), (6, 0), (15, 0), (18, 0))),
    "ero_later": IssuanceSchedule(_utc((8, 30), (20, 30))),
    "qpf_day1_2": IssuanceSchedule(_utc((6, 0), (10, 0), (18, 0), (22, 0))),
    "qpf_day3": IssuanceSchedule(_utc((8, 0), (20, 0))),
    "qpf_day4_7": IssuanceSchedule(_utc((9, 0),)),
    "winter_day1_3": IssuanceSchedule(_utc((10, 0), (22, 0))),
    "winter_day4_7": IssuanceSchedule(_utc((6, 30), (18, 30))),
    "surface": IssuanceSchedule(_utc((3, 0), (9, 0), (15, 0), (21, 0))),
    "mpd": IssuanceSchedule(_utc(*tuple((hour, 0) for hour in range(24))), 120, 90),
}


def wpc_schedule_for(product: dict) -> IssuanceSchedule:
    """Return the product-specific WPC cadence for a registry entry."""
    group = str(product.get("group") or "")
    days = tuple(int(day) for day in product.get("days") or ())
    day = int(product.get("day") or (days[0] if days else 1))
    if group == "ero":
        key = "ero_day1" if day == 1 else "ero_later"
    elif group == "qpf":
        max_day = max(days or (day,))
        key = "qpf_day1_2" if max_day <= 2 else "qpf_day3" if max_day == 3 else "qpf_day4_7"
    elif group == "winter":
        key = "winter_day1_3" if max(days or (day,)) <= 3 else "winter_day4_7"
    elif group == "mpd":
        key = "mpd"
    else:
        key = "surface"
    return _WPC_SCHEDULES[key]


def latest_usdm_valid_date(now: datetime | None = None) -> date:
    """Return the newest immutable Tuesday key released by Thursday 08:30 ET."""
    now_eastern = (now or datetime.now(UTC)).astimezone(EASTERN)
    days_since_thursday = (now_eastern.weekday() - 3) % 7
    release_day = now_eastern.date() - timedelta(days=days_since_thursday)
    release_at = datetime.combine(release_day, time(8, 30), EASTERN)
    if now_eastern < release_at:
        release_day -= timedelta(weeks=1)
    return release_day - timedelta(days=2)
