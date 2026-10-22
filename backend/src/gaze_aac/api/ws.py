"""WebSocket uç noktası.

Tek bağlantı üstünden iki yönlü akış: istemci bakış örnekleri ve komutlar
gönderir, sunucu yumuşatılmış konum, dwell ilerlemesi, seçim olayları ve
aday cümleler döner.

Mesaj gövdeleri ``schemas.messages`` içindeki modellerle doğrulanır; burada
elle JSON ayrıştırma yapılmaz, böylece sözleşme tek yerden değişir.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from ..config import get_settings
from ..gaze.calibration import CalibrationError
from ..nlp.expander import ExpansionService
from ..schemas.expansion import ExpansionRequest
from ..schemas.messages import (
    ClientCalibrationFit,
    ClientCalibrationSample,
    ClientExpand,
    ClientGazeSample,
    ClientHello,
    ClientMessage,
    ClientSelect,
    ClientSpeak,
    ClientTargets,
    ServerCalibrationResult,
    ServerCandidates,
    ServerDwellProgress,
    ServerError,
    ServerGaze,
    ServerMessage,
    ServerReady,
    ServerSelection,
)
from ..utils.logging import get_logger
from .session import GazeSession, SessionRegistry

logger = get_logger(__name__)
router = APIRouter()

_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
_server_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)

registry = SessionRegistry()


async def _send(websocket: WebSocket, message: ServerMessage) -> None:
    await websocket.send_text(_server_adapter.dump_json(message).decode())


async def _handle_message(
    message: ClientMessage,
    session: GazeSession,
    websocket: WebSocket,
    expansion: ExpansionService,
) -> None:
    """Tek bir istemci mesajını işler."""
    if isinstance(message, ClientHello):
        session.screen_width = message.screen_width
        session.screen_height = message.screen_height
        session.participant_id = message.participant_id
        return

    if isinstance(message, ClientTargets):
        session.set_targets(message.targets)
        return

    if isinstance(message, ClientGazeSample):
        point = message.point
        x, y, event = session.process_gaze(point.x, point.y, point.t)

        await _send(websocket, ServerGaze(x=x, y=y, t=point.t))

        if event.selected and event.target_id:
            await _send(
                websocket,
                ServerSelection(target_id=event.target_id, dwell_ms=event.elapsed_ms),
            )
        elif event.target_id and event.progress > 0.0:
            await _send(
                websocket,
                ServerDwellProgress(target_id=event.target_id, progress=event.progress),
            )
        return

    if isinstance(message, ClientSelect):
        await _send(websocket, ServerSelection(target_id=message.target_id, dwell_ms=0.0))
        return

    if isinstance(message, ClientCalibrationSample):
        session.add_calibration_sample(message.features, message.target_x, message.target_y)
        return

    if isinstance(message, ClientCalibrationFit):
        try:
            report = session.fit_calibration()
        except CalibrationError as exc:
            await _send(
                websocket,
                ServerCalibrationResult(
                    ok=False, sample_count=len(session.calibration_samples), message=str(exc)
                ),
            )
            return

        await _send(
            websocket,
            ServerCalibrationResult(
                ok=True,
                sample_count=report.sample_count,
                mean_error_px=report.mean_error_px,
                mean_error_deg=report.mean_error_deg,
            ),
        )
        return

    if isinstance(message, ClientExpand):
        result = await expansion.expand(
            ExpansionRequest(
                abbreviation=message.abbreviation,
                scheme=message.scheme,
                context=message.context,
                top_k=message.top_k,
            )
        )
        await _send(
            websocket,
            ServerCandidates(
                abbreviation=message.abbreviation,
                scheme=message.scheme,
                candidates=result.candidates,
                latency_ms=result.latency_ms,
            ),
        )
        return

    if isinstance(message, ClientSpeak):
        # Seslendirme tarayıcıda yapılıyor; sunucu yalnızca ölçüm için kaydeder.
        logger.info("[%s] seslendirildi: %s", session.session_id, message.text)
        return


@router.websocket("/ws")
async def gaze_socket(websocket: WebSocket) -> None:
    """Bakış akışı ve genişletme için ana kanal."""
    await websocket.accept()

    settings = get_settings()
    expansion: ExpansionService = websocket.app.state.expansion
    session = registry.create(settings)

    try:
        await _send(
            websocket,
            ServerReady(
                session_id=session.session_id,
                gaze_source=settings.gaze_source,
                expander_provider=expansion.provider_name,
                dwell_ms=settings.dwell_ms,
            ),
        )

        while True:
            raw = await websocket.receive_text()
            try:
                message = _client_adapter.validate_json(raw)
            except ValidationError as exc:
                # Bağlantıyı kapatma: tek bozuk mesaj oturumu düşürmemeli.
                await _send(
                    websocket,
                    ServerError(code="invalid_message", detail=exc.errors()[0].get("msg", "")),
                )
                continue

            await _handle_message(message, session, websocket, expansion)

    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - beklenmeyen hata
        logger.exception("WebSocket oturumu hata ile kapandı: %s", session.session_id)
    finally:
        registry.remove(session.session_id)
