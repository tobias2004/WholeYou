from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PatientSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    birthDate: str | None = None
    gender: str | None = None


class EpicSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    connected: bool
    source: str | None = None
    patient: PatientSummary | None = None
    labs: list[dict[str, Any]] = Field(default_factory=list)
    vitals: list[dict[str, Any]] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    medications: list[dict[str, Any]] = Field(default_factory=list)
    allergies: list[dict[str, Any]] = Field(default_factory=list)
    encounters: list[dict[str, Any]] = Field(default_factory=list)
    diagnosticReports: list[dict[str, Any]] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
