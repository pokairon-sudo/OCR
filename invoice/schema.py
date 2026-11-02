"""Pydantic models describing an extracted invoice.

Validators are intentionally defensive: they clean whitespace and drop
empty rows, but never "repair" numbers. Silent repair hides the real bugs.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class LineItem(BaseModel):
    name: str = Field(description="Persian product name, spaces preserved")
    weight: str = Field(default="", description="وزن column, e.g. 0/590")
    quantity: str = Field(default="", description="تعداد column, e.g. 2")
    unit_price: str = Field(default="0", description="فی / قیمت واحد")
    total_price: str = Field(default="0", description="جمع")

    @field_validator("name")
    @classmethod
    def _squash_whitespace(cls, v: str) -> str:
        v = str(v).replace("\u200c", " ")
        return re.sub(r"\s+", " ", v).strip()


class Invoice(BaseModel):
    items: list[LineItem] = Field(default_factory=list)
    grand_total: str = Field(default="0", description="جمع کل")
    total_weight: str = Field(default="", description="وزن کل, e.g. 4/570 kg")
