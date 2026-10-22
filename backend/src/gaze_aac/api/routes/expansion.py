"""HTTP üstünden kısaltma genişletme.

WebSocket asıl kanaldır; bu uç nokta test, betik ve Swagger üstünden elle
deneme için var. Aynı servisi kullanır, bu yüzden davranış farkı olmaz.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ...nlp.schemes import get_scheme
from ...schemas.expansion import ExpansionRequest, ExpansionResult

router = APIRouter(prefix="/expand", tags=["genisletme"])


@router.post("", response_model=ExpansionResult)
async def expand(payload: ExpansionRequest, request: Request) -> ExpansionResult:
    """Kısaltmayı aday cümlelere çevirir."""
    try:
        get_scheme(payload.scheme)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return await request.app.state.expansion.expand(payload)


@router.post("/abbreviate", response_model=dict[str, str])
def abbreviate(sentence: str, scheme: str = "S1") -> dict[str, str]:
    """Cümleyi kısaltmaya çevirir. Veri üretimi ve hata ayıklama için."""
    try:
        handler = get_scheme(scheme)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "sentence": sentence,
        "scheme": handler.id,
        "abbreviation": handler.abbreviate(sentence),
    }
