from typing import Any

from pydantic import BaseModel, Field


class WearableProvider(BaseModel):
    id: str
    name: str
    type: str | None = None
    supportsOAuth: bool = False
    supportsImport: bool = False
    requiresMobile: bool = False
    logoUrl: str | None = None
    enabled: bool = True


class WearableConnection(BaseModel):
    provider: str
    status: str | None = None
    providerUserId: str | None = None
    scopes: list[str] = Field(default_factory=list)
    connectedAt: str | None = None
    lastSyncedAt: str | None = None
    source: str = "open_wearables"


class WearableSource(BaseModel):
    provider: str | None = None
    device: str | None = None
    deviceType: str | None = None


class WearableTimeseriesPoint(BaseModel):
    timestamp: str | None = None
    type: str | None = None
    value: Any = None
    unit: str | None = None
    zoneOffset: str | None = None
    source: WearableSource = Field(default_factory=WearableSource)


class WorkoutEvent(BaseModel):
    id: str | None = None
    type: str | None = None
    startTime: str | None = None
    endTime: str | None = None
    durationMinutes: float | None = None
    calories: float | None = None
    distance: float | None = None
    averageHeartRate: float | None = None
    source: WearableSource = Field(default_factory=WearableSource)


class SleepEvent(BaseModel):
    id: str | None = None
    startTime: str | None = None
    endTime: str | None = None
    durationMinutes: float | None = None
    efficiencyPercent: float | None = None
    stages: list[dict[str, Any]] = Field(default_factory=list)
    interruptions: int | None = None
    source: WearableSource = Field(default_factory=WearableSource)


class HealthScoreComponent(BaseModel):
    value: float | int | str | None = None
    qualifier: str | None = None


class HealthScore(BaseModel):
    id: str | None = None
    dataSourceId: str | None = None
    provider: str | None = None
    category: str
    value: float | int | str | None = None
    qualifier: str | None = None
    recordedAt: str | None = None
    zoneOffset: str | None = None
    components: dict[str, HealthScoreComponent | dict[str, Any]] = Field(default_factory=dict)


class WearableSummary(BaseModel):
    connected: bool
    source: str = "open_wearables"
    connections: list[WearableConnection] = Field(default_factory=list)
    timeseries: list[WearableTimeseriesPoint] = Field(default_factory=list)
    workouts: list[WorkoutEvent] = Field(default_factory=list)
    sleep: list[SleepEvent] = Field(default_factory=list)
    generatedAt: str | None = None
    message: str | None = None


class ProviderConnectResponse(BaseModel):
    provider: str
    authorizationUrl: str | None = None
    state: str | None = None
    mode: str | None = None


class ProviderConnectRequest(BaseModel):
    mode: str = "synthetic"


class SyncRequest(BaseModel):
    provider: str | None = None
    async_: bool | None = Field(default=None, alias="async")


class HistoricalSyncRequest(BaseModel):
    startDate: str | None = None
    endDate: str | None = None
    provider: str | None = None


class SyntheticDataRequest(BaseModel):
    seed: int | None = None
    preset: str = "minimal"
    numUsers: int = Field(default=1, ge=1, le=10)


class SyntheticDataResponse(BaseModel):
    task_id: str
    status: str
    seed_used: int | None = None
    preset: str | None = None
    num_users: int | None = None
