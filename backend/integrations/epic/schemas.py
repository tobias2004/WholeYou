from typing import Any

from pydantic import BaseModel, Field


class PatientProfile(BaseModel):
    id: str | None = None
    name: str | None = None
    birthDate: str | None = None
    gender: str | None = None


class Condition(BaseModel):
    id: str | None = None
    name: str | None = None
    code: str | None = None
    clinicalStatus: str | None = None
    verificationStatus: str | None = None
    recordedDate: str | None = None
    source: str = "epic"


class Medication(BaseModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    dosageText: str | None = None
    authoredOn: str | None = None
    source: str = "epic"


class LabResult(BaseModel):
    id: str | None = None
    name: str | None = None
    code: str | None = None
    value: Any = None
    unit: str | None = None
    referenceRange: str | None = None
    interpretation: str | None = None
    effectiveDateTime: str | None = None
    source: str = "epic"


class Vital(BaseModel):
    id: str | None = None
    name: str | None = None
    code: str | None = None
    value: Any = None
    unit: str | None = None
    effectiveDateTime: str | None = None
    source: str = "epic"


class Encounter(BaseModel):
    id: str | None = None
    type: str | None = None
    periodStart: str | None = None
    periodEnd: str | None = None
    reason: str | None = None
    provider: str | None = None
    source: str = "epic"


class ClinicalSummary(BaseModel):
    connected: bool = True
    patient: PatientProfile | None = None
    conditions: list[Condition] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    labs: list[LabResult] = Field(default_factory=list)
    vitals: list[Vital] = Field(default_factory=list)
    encounters: list[Encounter] = Field(default_factory=list)
    generatedAt: str | None = None
    message: str | None = None
