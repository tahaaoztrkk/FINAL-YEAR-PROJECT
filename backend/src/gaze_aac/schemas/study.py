"""Kullanıcı testi planının şemaları.

Plan sunucuda kurulur ve istemciye bu biçimde gider: sıra dengeleme ve cümle
setleri tek yerde karar verilsin, arayüz yalnızca planı izlesin.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Condition = Literal["A", "B"]


class StudyTrial(BaseModel):
    """Katılımcının yazacağı tek hedef cümle."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0, description="Blok içindeki sıra")
    text: str = Field(description="Hedef cümle")
    practice: bool = Field(description="Alıştırma cümlesi mi; analize girmez")


class StudyBlock(BaseModel):
    """Bir koşulun cümleleri: önce alıştırma, sonra ölçülen set."""

    model_config = ConfigDict(extra="forbid")

    condition: Condition = Field(description="A: harf harf, B: kısaltma ve aday listesi")
    scheme: str = Field(description="B koşulunda kullanılan kısaltma şeması")
    trials: list[StudyTrial]
