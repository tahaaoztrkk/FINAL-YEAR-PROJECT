"""WebSocket uç noktası.

Tek bağlantı üstünden iki yönlü akış: istemci bakış örnekleri ve komutlar
gönderir, sunucu yumuşatılmış konum, dwell ilerlemesi, seçim olayları ve
aday cümleler döner.

Mesaj gövdeleri ``schemas.messages`` içindeki modellerle doğrulanır; burada
elle JSON ayrıştırma yapılmaz, böylece sözleşme tek yerden değişir.

Kullanıcı testi başlatıldıysa (``study_start``) her olay aynı yerde oturum
kaydına da yazılır. Kayıt sunucuda tutulur: zaman damgaları tek saatten
gelir ve tarayıcı sekmesi kapansa bile o ana kadarki olaylar diskte kalır.
"""

from __future__ import annotations

from datetime import datetime

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
    ClientStudyEnd,
    ClientStudyStart,
    ClientTargets,
    ClientTrialEnd,
    ClientTrialStart,
    ServerCalibrationResult,
    ServerCandidates,
    ServerDwellProgress,
    ServerError,
    ServerGaze,
    ServerMessage,
    ServerReady,
    ServerSelection,
    ServerStudyPlan,
)
from ..schemas.study import StudyBlock, StudyTrial
from ..study.protocol import (
    StudyMaterials,
    build_plan,
    normalize_participant_id,
    sentences_match,
)
from ..study.recorder import SessionRecorder, loggable_features
from ..utils.logging import get_logger
from .session import GazeSession, SessionRegistry

logger = get_logger(__name__)
router = APIRouter()

_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
_server_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)

registry = SessionRegistry()


async def _send(websocket: WebSocket, message: ServerMessage) -> None:
    await websocket.send_text(_server_adapter.dump_json(message).decode())


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _find_trial(
    session: GazeSession, block_index: int, trial_index: int
) -> tuple[StudyBlock, StudyTrial] | None:
    if block_index >= len(session.study_plan):
        return None
    block = session.study_plan[block_index]
    if trial_index >= len(block.trials):
        return None
    return block, block.trials[trial_index]


async def _start_study(
    message: ClientStudyStart,
    session: GazeSession,
    websocket: WebSocket,
    expansion: ExpansionService,
) -> None:
    settings = session.settings
    try:
        participant_id = normalize_participant_id(message.participant_id)
    except ValueError as exc:
        await _send(websocket, ServerError(code="invalid_participant", detail=str(exc)))
        return

    try:
        materials = StudyMaterials.load(settings.study_sentences_path)
    except FileNotFoundError:
        await _send(
            websocket,
            ServerError(
                code="study_materials_missing",
                detail=f"Deney cümleleri bulunamadı: {settings.study_sentences_path}",
            ),
        )
        return
    except ValueError as exc:
        await _send(websocket, ServerError(code="study_materials_invalid", detail=str(exc)))
        return

    plan = build_plan(participant_id, materials)
    order = "".join(block.condition for block in plan)

    # Aynı bağlantıda ikinci başlatma (ör. kod yanlış girildi) eski kaydı kapatır.
    session.stop_recording()
    session.participant_id = participant_id
    session.study_plan = plan
    session.last_candidates = []
    session.recorder = SessionRecorder.create(
        settings.sessions_dir, participant_id, session.session_id
    )
    # Koşulların hangi ayarlarla koştuğu kaydın başında durur: yanlış
    # sağlayıcıyla toplanan veri sonradan buradan ayıklanır.
    session.log(
        "study_start",
        participant_id=participant_id,
        session_id=session.session_id,
        wall=_now(),
        order=order,
        scheme=materials.scheme,
        materials=materials.digest,
        provider=expansion.provider_name,
        gaze_source=settings.gaze_source,
        dwell_ms=settings.dwell_ms,
        dwell_cancel_ms=settings.dwell_cancel_ms,
        smoothing_window=settings.smoothing_window,
        screen=[session.screen_width, session.screen_height],
    )
    logger.info("[%s] kullanıcı testi: %s, sıra %s", session.session_id, participant_id, order)
    await _send(websocket, ServerStudyPlan(participant_id=participant_id, order=order, blocks=plan))


async def _handle_trial(
    message: ClientTrialStart | ClientTrialEnd, session: GazeSession, websocket: WebSocket
) -> None:
    if not session.study_plan:
        await _send(
            websocket,
            ServerError(code="study_not_started", detail="Önce study_start gönderin."),
        )
        return

    found = _find_trial(session, message.block_index, message.trial_index)
    if found is None:
        await _send(
            websocket,
            ServerError(
                code="unknown_trial",
                detail=f"Planda yok: blok {message.block_index}, cümle {message.trial_index}",
            ),
        )
        return

    block, trial = found
    if isinstance(message, ClientTrialStart):
        # Önceki cümlenin adayları bu cümlede söylenirse sıra yanlış yazılır.
        session.last_candidates = []
        session.log(
            "trial_start",
            block_index=message.block_index,
            trial_index=message.trial_index,
            condition=block.condition,
            scheme=block.scheme,
            target=trial.text,
            practice=trial.practice,
        )
        return

    session.log(
        "trial_end",
        block_index=message.block_index,
        trial_index=message.trial_index,
        outcome=message.outcome,
        output=message.output,
        target=trial.text,
        correct=sentences_match(message.output, trial.text),
        practice=trial.practice,
    )


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
        session.log(
            "targets",
            targets=[
                target.model_dump(include={"id", "x", "y", "width", "height"})
                for target in message.targets
            ],
        )
        return

    if isinstance(message, ClientGazeSample):
        point = message.point
        x, y, event = session.process_gaze(point.x, point.y, point.t)
        session.log(
            "gaze",
            x=round(point.x, 4),
            y=round(point.y, 4),
            sx=round(x, 4),
            sy=round(y, 4),
            client_t=point.t,
            confidence=point.confidence,
        )

        await _send(websocket, ServerGaze(x=x, y=y, t=point.t))

        if event.selected and event.target_id:
            session.log(
                "selection", target_id=event.target_id, dwell_ms=event.elapsed_ms, via="dwell"
            )
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
        session.dwell.lock(message.target_id)
        session.log("selection", target_id=message.target_id, dwell_ms=0.0, via="click")
        await _send(websocket, ServerSelection(target_id=message.target_id, dwell_ms=0.0))
        return

    if isinstance(message, ClientCalibrationSample):
        session.add_calibration_sample(message.features, message.target_x, message.target_y)
        session.log(
            "calibration_sample",
            target_x=message.target_x,
            target_y=message.target_y,
            features=loggable_features(message.features),
            feature_count=len(message.features),
        )
        return

    if isinstance(message, ClientCalibrationFit):
        try:
            report = session.fit_calibration()
        except CalibrationError as exc:
            calibration = ServerCalibrationResult(
                ok=False, sample_count=len(session.calibration_samples), message=str(exc)
            )
        else:
            calibration = ServerCalibrationResult(
                ok=True,
                sample_count=report.sample_count,
                mean_error_px=report.mean_error_px,
                mean_error_deg=report.mean_error_deg,
            )
        session.log("calibration_result", **calibration.model_dump(exclude={"type"}))
        await _send(websocket, calibration)
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
        session.last_candidates = [c.text for c in result.candidates if c.valid]
        # Geçersiz adaylar da yazılır: modelin ne kadar saptığı buradan ölçülür.
        session.log(
            "expand",
            abbreviation=message.abbreviation,
            scheme=message.scheme,
            context=message.context,
            top_k=message.top_k,
            provider=result.provider,
            latency_ms=round(result.latency_ms, 1),
            candidates=[c.model_dump() for c in result.candidates],
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
        session.log("speak", text=message.text, candidate_rank=session.candidate_rank(message.text))
        return

    if isinstance(message, ClientStudyStart):
        await _start_study(message, session, websocket, expansion)
        return

    if isinstance(message, ClientTrialStart | ClientTrialEnd):
        await _handle_trial(message, session, websocket)
        return

    if isinstance(message, ClientStudyEnd):
        session.log("study_end", wall=_now())
        session.stop_recording()
        session.study_plan = []
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
        # Deney bitmeden kopan bağlantı kayıtta görünsün; analiz o cümleyi
        # yeni bağlantıdaki tekrarından alır.
        session.log("disconnect", wall=_now())
        session.stop_recording()
        registry.remove(session.session_id)
