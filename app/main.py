import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.config import get_settings
from app.schemas import HealthResponse, SynthesisRequest, VoicesResponse
from app.services.mimo_tts import MimoTtsError, MimoTtsService


STATIC_DIR = Path(__file__).resolve().parent / "static"
SUPPORTED_MODES = ["preset", "voice_design", "voice_clone"]
AUDIO_TAG_EXAMPLES = [
    "(温柔)你好，欢迎来到今天的节目。",
    "[笑]这件事情听起来很有意思。",
    "[叹气]我们还是从头开始吧。",
    "(四川话)今天我们来聊一个轻松的话题。",
    "(唱歌)啦啦啦，阳光洒在窗台上。",
]
VOICE_DESIGN_TEMPLATES = [
    "年轻女性，声线清亮、有亲和力，语速自然偏轻快，像播客主持人一样放松但吐字清楚，适合知识讲解和日常介绍。",
    "成熟男性，低沉稳重，气息稳定，语速中等偏慢，像纪录片旁白，带一点故事感但不过分夸张。",
    "专业新闻播报音色，中性偏成熟，吐字标准，节奏平稳，情绪克制，适合公告、新闻和正式说明。",
    "温柔客服女声，亲切、耐心、清晰，语速适中，句尾轻微上扬，听起来可靠且不机械。",
    "悬疑故事旁白，声线偏低，语速克制，停顿明显，带一点紧张感和神秘感，适合悬疑、案件和氛围叙述。",
]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _build_ws_synthesis_request(
    websocket: WebSocket,
    settings,
    text: str,
    overrides: dict[str, str | None] | None = None,
) -> SynthesisRequest:
    params = websocket.query_params
    merged = {
        "mode": settings.tts_ws_default_mode,
        "voice": settings.tts_ws_default_voice,
        "style_prompt": settings.tts_ws_default_style_prompt,
        "voice_design_prompt": settings.tts_ws_default_voice_design_prompt,
        "voice_clone_audio": None,
    }

    for key in ("mode", "voice", "style_prompt", "voice_design_prompt", "voice_clone_audio"):
        value = params.get(key)
        if value is not None:
            merged[key] = value

    if overrides:
        for key, value in overrides.items():
            if value is not None:
                merged[key] = value

    payload = {
        "mode": merged["mode"],
        "text": text,
        "voice": _normalize_optional_text(merged["voice"]),
        "style_prompt": _normalize_optional_text(merged["style_prompt"]),
        "voice_design_prompt": _normalize_optional_text(merged["voice_design_prompt"]),
        "voice_clone_audio": _normalize_optional_text(merged["voice_clone_audio"]),
    }
    return SynthesisRequest.model_validate(payload)


def _parse_ws_message(message: str) -> tuple[str, dict[str, str | None]]:
    text = message.strip()
    if not text:
        return "", {}

    if not text.startswith("{"):
        return text, {}

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text, {}

    if not isinstance(payload, dict):
        return text, {}

    raw_text = str(payload.get("text", "")).strip()
    overrides = {
        "mode": _normalize_optional_text(payload.get("mode")),
        "voice": _normalize_optional_text(payload.get("voice")),
        "style_prompt": _normalize_optional_text(payload.get("style_prompt")),
        "voice_design_prompt": _normalize_optional_text(payload.get("voice_design_prompt")),
        "voice_clone_audio": _normalize_optional_text(payload.get("voice_clone_audio")),
    }
    return raw_text, overrides


async def _send_text_safely(
    websocket: WebSocket,
    lock: asyncio.Lock,
    message: str,
) -> None:
    async with lock:
        await websocket.send_text(message)


async def _send_bytes_safely(
    websocket: WebSocket,
    lock: asyncio.Lock,
    payload: bytes,
) -> None:
    async with lock:
        await websocket.send_bytes(payload)


async def _pong_keepalive(
    websocket: WebSocket,
    lock: asyncio.Lock,
    interval_seconds: float = 5.0,
) -> None:
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            await _send_text_safely(websocket, lock, json.dumps({"type": "pong"}))
    except (RuntimeError, WebSocketDisconnect):
        return
    except asyncio.CancelledError:
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.mimo_tts = MimoTtsService(settings)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Xiaomi MiMo Local TTS Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/styles.css", include_in_schema=False)
    async def styles() -> FileResponse:
        return FileResponse(STATIC_DIR / "styles.css", media_type="text/css")

    @app.get("/app.js", include_in_schema=False)
    async def script() -> FileResponse:
        return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        settings = app.state.settings
        return HealthResponse(
            status="ok",
            has_api_key=settings.has_api_key,
            mimo_base_url=settings.mimo_base_url,
        )

    @app.get("/api/v1/voices", response_model=VoicesResponse)
    async def voices() -> VoicesResponse:
        service: MimoTtsService = app.state.mimo_tts
        return VoicesResponse(
            modes=SUPPORTED_MODES,
            voices=service.voices,
            audio_tag_examples=AUDIO_TAG_EXAMPLES,
            voice_design_templates=VOICE_DESIGN_TEMPLATES,
        )

    @app.post(
        "/api/v1/speech/synthesize",
        responses={
            200: {"content": {"audio/wav": {}}},
            502: {"description": "上游 TTS 服务失败"},
        },
    )
    async def synthesize(payload: SynthesisRequest) -> Response:
        service: MimoTtsService = app.state.mimo_tts
        try:
            audio_bytes = await service.synthesize(payload)
        except MimoTtsError as exc:
            detail = str(exc)
            status_code = 400 if detail.startswith("不支持的预置音色") else 502
            raise HTTPException(status_code=status_code, detail=detail) from exc

        headers = service.build_download_headers()
        return Response(content=audio_bytes, media_type="audio/wav", headers=headers)

    @app.websocket("/virtualhuman/speech/synthesis/1103")
    async def websocket_synthesize(websocket: WebSocket) -> None:
        await websocket.accept()
        settings = app.state.settings
        service: MimoTtsService = app.state.mimo_tts
        send_lock = asyncio.Lock()
        keepalive_task = asyncio.create_task(_pong_keepalive(websocket, send_lock))

        try:
            await _send_text_safely(websocket, send_lock, "connect-success")

            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                text_message = message.get("text")
                bytes_message = message.get("bytes")

                if text_message is not None:
                    if text_message == "ping":
                        await _send_text_safely(
                            websocket,
                            send_lock,
                            json.dumps({"type": "pong"}),
                        )
                        continue

                    speech_text, overrides = _parse_ws_message(text_message)
                    if not speech_text:
                        continue

                    try:
                        payload = _build_ws_synthesis_request(
                            websocket=websocket,
                            settings=settings,
                            text=speech_text,
                            overrides=overrides,
                        )
                        wav_bytes = await service.synthesize(payload)
                        pcm_bytes = service.wav_to_pcm_s16le_mono_16k(wav_bytes)
                    except (MimoTtsError, ValidationError) as exc:
                        await _send_text_safely(
                            websocket,
                            send_lock,
                            f"data=error message={exc}",
                        )
                        continue

                    for chunk in service.iter_pcm_chunks(
                        pcm_bytes,
                        settings.tts_ws_chunk_duration_ms,
                    ):
                        await _send_bytes_safely(websocket, send_lock, chunk)
                        await asyncio.sleep(0)
                    continue

                if bytes_message is not None:
                    if bytes_message in (b"", b"ping"):
                        await _send_text_safely(
                            websocket,
                            send_lock,
                            json.dumps({"type": "pong"}),
                        )
                    continue
        except WebSocketDisconnect:
            return
        finally:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return app


app = create_app()
