import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SleepScoreResult:
    overall_score: int
    components: dict[str, dict[str, float | int | None]]


@dataclass(frozen=True)
class ResilienceScoreResult:
    hrv_cv: float
    resilience_score: int
    metric_type: str
    days_counted: int


def calculate_sleep_score(
    sleep_event: dict[str, Any],
    historical_sleep_events: list[dict[str, Any]],
) -> SleepScoreResult | None:
    total_sleep_minutes = _number(sleep_event.get("duration_minutes"))
    if total_sleep_minutes is None or total_sleep_minutes <= 0 or total_sleep_minutes > 24 * 60:
        return None

    stage_minutes = _stage_minutes(sleep_event.get("stages") or [])
    deep_minutes = stage_minutes.get("deep", 0.0)
    rem_minutes = stage_minutes.get("rem", 0.0)
    awake_minutes = stage_minutes.get("awake", 0.0)
    if awake_minutes == 0 and sleep_event.get("efficiency_percent") is not None:
        efficiency = max(0.0, min(100.0, float(sleep_event["efficiency_percent"])))
        awake_minutes = total_sleep_minutes * ((100.0 - efficiency) / 100.0)

    duration_score = _score_duration_hours(total_sleep_minutes / 60.0)
    stages_score = _score_stages(deep_minutes, rem_minutes)
    consistency_score = _score_consistency(
        _parse_datetime(sleep_event.get("start_time")),
        [_parse_datetime(event.get("start_time")) for event in historical_sleep_events],
    )
    interruptions_score = _score_interruptions(
        awake_minutes,
        int(sleep_event.get("interruptions") or 0),
    )

    overall = int(
        duration_score * 0.40
        + stages_score * 0.20
        + consistency_score * 0.20
        + interruptions_score * 0.20
    )
    return SleepScoreResult(
        overall_score=_clamp_int(overall, 0, 100),
        components={
            "duration": {"value": duration_score},
            "stages": {"value": stages_score},
            "consistency": {"value": consistency_score},
            "interruptions": {"value": interruptions_score},
        },
    )


def calculate_resilience_score(
    timeseries: list[dict[str, Any]],
    *,
    lookback_days: int = 7,
    min_days_required: int = 5,
) -> ResilienceScoreResult | None:
    grouped, metric_type = _daily_hrv_values(timeseries, "heart_rate_variability_rmssd")
    if not grouped:
        grouped, metric_type = _daily_hrv_values(timeseries, "heart_rate_variability_sdnn")
    if not grouped or len(grouped) < min_days_required:
        return None

    recent_days = sorted(grouped)[-lookback_days:]
    daily_averages = [
        sum(grouped[day]) / len(grouped[day])
        for day in recent_days
        if grouped[day]
    ]
    if len(daily_averages) < min_days_required:
        return None

    hrv_cv = _coefficient_of_variation(daily_averages)
    if hrv_cv is None:
        return None
    return ResilienceScoreResult(
        hrv_cv=round(hrv_cv, 3),
        resilience_score=_hrv_cv_to_resilience_score(hrv_cv),
        metric_type=metric_type,
        days_counted=len(daily_averages),
    )


def _stage_minutes(stages: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for stage in stages:
        stage_name = str(stage.get("stage") or "").lower()
        minutes = _number(stage.get("minutes"))
        if minutes is None:
            start = _parse_datetime(stage.get("start_time") or stage.get("startTime"))
            end = _parse_datetime(stage.get("end_time") or stage.get("endTime"))
            minutes = (end - start).total_seconds() / 60 if start and end and end > start else None
        if stage_name and minutes is not None:
            if stage_name in {"asleep", "sleeping"}:
                stage_name = "light"
            totals[stage_name] = totals.get(stage_name, 0.0) + minutes
    return totals


def _score_duration_hours(duration_hours: float) -> int:
    if 7.0 <= duration_hours <= 9.0:
        return 100
    if duration_hours < 7.0:
        return _clamp_int(100 / (1 + math.exp(-1.5 * (duration_hours - 5.0))), 0, 100)
    return _clamp_int(max(50.0, 100 / (1 + math.exp(0.8 * (duration_hours - 11.0)))), 0, 100)


def _score_stages(deep_minutes: float, rem_minutes: float) -> int:
    deep_score = _clamp_int((deep_minutes / 90.0) * 100, 0, 100)
    rem_score = _clamp_int((rem_minutes / 90.0) * 100, 0, 100)
    return _clamp_int((deep_score * 0.5) + (rem_score * 0.5), 0, 100)


def _score_consistency(session_start: datetime | None, history: list[datetime | None]) -> int:
    valid_history = [item for item in history if item is not None]
    if not session_start or not valid_history:
        return 0
    median_hours = statistics.median(_hours_past_noon(item) for item in valid_history)
    diff_minutes = (_hours_past_noon(session_start) - median_hours) * 60
    grace = 15.0
    if abs(diff_minutes) <= grace:
        return 100
    if diff_minutes > 0:
        penalty = ((diff_minutes - grace) / 105.0) * 100
    else:
        penalty = min(20.0, ((abs(diff_minutes) - grace) / 105.0) * 100)
    return _clamp_int(100 - penalty, 0, 100)


def _score_interruptions(awake_minutes: float, interruption_count: int) -> int:
    duration_score = 80.0
    if awake_minutes > 20:
        duration_score = max(0.0, 80.0 - (((awake_minutes - 20) / 70.0) * 80.0))
    frequency_fractions = (1.0, 1.0, 0.75, 0.5, 0.0)
    frequency_score = 20.0 * frequency_fractions[min(interruption_count, len(frequency_fractions) - 1)]
    return _clamp_int(duration_score + frequency_score, 0, 100)


def _daily_hrv_values(timeseries: list[dict[str, Any]], metric_type: str) -> tuple[dict[str, list[float]], str]:
    grouped: dict[str, list[float]] = {}
    for point in timeseries:
        if point.get("type") != metric_type:
            continue
        timestamp = _parse_datetime(point.get("timestamp"))
        value = _number(point.get("value"))
        if timestamp is None or value is None or value <= 0:
            continue
        grouped.setdefault(timestamp.date().isoformat(), []).append(value)
    metric_label = "RMSSD" if metric_type.endswith("rmssd") else "SDNN"
    return grouped, metric_label


def _coefficient_of_variation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = statistics.mean(values)
    if mean <= 0:
        return None
    return statistics.stdev(values) / mean


def _hrv_cv_to_resilience_score(hrv_cv: float) -> int:
    cv_pct = hrv_cv * 100.0
    if cv_pct <= 7.0:
        return 100
    if cv_pct >= 40.0:
        return 0
    return _clamp_int(100.0 * (40.0 - cv_pct) / (40.0 - 7.0), 0, 100)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _hours_past_noon(value: datetime) -> float:
    hours = value.hour + value.minute / 60 + value.second / 3600
    return hours - 12 if hours >= 12 else hours + 12


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp_int(value: float, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, round(value)))
