from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, model_validator


def require_time(value: object) -> object:
    if isinstance(value, str) and "T" not in value and " " not in value:
        raise ValueError("a deadline needs both date and time, e.g. 2026-11-20T09:00:00")
    return value


Deadline = Annotated[datetime, BeforeValidator(require_time)]
Money = Annotated[Decimal, Field(ge=0)]
Percentage = Annotated[Decimal, Field(ge=0, le=100)]


class SiteVisit(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    NOT_REQUIRED = "not_required"


class SmallBusinessPreference(StrEnum):
    EXCLUSIVE = "exclusive"
    QUOTA = "quota"
    PREFERENCE = "preference"
    NONE = "none"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=500)


class FieldResult[T](StrictModel):
    status: Literal["found", "not_found"]
    value: T | None = None
    evidence: Evidence | None = None

    @model_validator(mode="after")
    def check_consistency(self) -> Self:
        if self.status == "found":
            if self.value is None:
                raise ValueError("a found field needs a value")
            if self.evidence is None:
                raise ValueError("a found field needs evidence")
        elif self.value is not None or self.evidence is not None:
            raise ValueError("a not_found field must have no value and no evidence")
        return self


def not_found[T]() -> FieldResult[T]:
    return FieldResult(status="not_found")


class TenderExtraction(StrictModel):
    proposal_deadline: FieldResult[Deadline]
    estimated_value: FieldResult[Money]
    requires_technical_certificate: FieldResult[StrictBool]
    bid_bond_percentage: FieldResult[Percentage]
    performance_bond_percentage: FieldResult[Percentage]
    site_visit: FieldResult[SiteVisit]
    small_business_preference: FieldResult[SmallBusinessPreference]

    @classmethod
    def blank(cls) -> Self:
        return cls(
            proposal_deadline=not_found(),
            estimated_value=not_found(),
            requires_technical_certificate=not_found(),
            bid_bond_percentage=not_found(),
            performance_bond_percentage=not_found(),
            site_visit=not_found(),
            small_business_preference=not_found(),
        )


FIELD_NAMES = tuple(TenderExtraction.model_fields)


class GoldAnnotation(StrictModel):
    control_number: str = Field(min_length=1)
    document_sequence: int = Field(ge=1)
    annotator: str = Field(min_length=1)
    annotated_on: date
    extraction: TenderExtraction
    notes: str = ""
