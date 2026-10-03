from typing import Literal

from pydantic import BaseModel, Field


class ReportIn(BaseModel):
    kind: Literal["accident", "hazard", "pothole", "poor_lighting", "waterlogging"]
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    description: str = Field(default="", max_length=300)


class ReviewIn(BaseModel):
    status: Literal["approved", "rejected"]
