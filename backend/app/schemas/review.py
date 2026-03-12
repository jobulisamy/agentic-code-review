from typing import Literal

from pydantic import BaseModel

Category = Literal["bug", "security", "style", "performance", "test_coverage"]
Severity = Literal["error", "warning", "info"]


class Finding(BaseModel):
    category: Category
    severity: Severity
    line_start: int
    line_end: int
    title: str
    description: str
    suggestion: str


class ReviewRequest(BaseModel):
    code: str
    language: str = "python"


class ReviewResponse(BaseModel):
    findings: list[Finding] = []
