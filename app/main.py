import asyncio
import audioop
import base64
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.config import get_settings
from app.schemas import AsrRequest, AsrResponse, HealthResponse, SynthesisRequest, VoicesResponse
from app.services.mimo_asr import MimoAsrError, MimoAsrService
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
VOICE_DESIGN_TEMPLATES: dict[str, str] = {
    "新闻播报": "专业新闻播报音色，中性偏成熟，吐字标准，节奏平稳，情绪克制，适合公告、新闻和正式说明。",
    "课程讲师": "亲切课程讲师音色，声音清楚、耐心、有条理，语速中等偏慢，重点词会自然强调，适合教学和培训。",
    "商务汇报女声": "沉稳商务女声，语气自信、清晰、克制，语速中等，适合汇报、课程开场和企业宣传。",
    "温柔客服": "温柔客服女声，亲切、耐心、清晰，语速适中，句尾轻微上扬，听起来可靠且不机械。",
    "品牌旁白女声": "冷静旁白女声，声线干净，情绪克制，语速平稳，带一点高级感，适合展览导览、品牌片和城市宣传。",
    "清亮播客女声": "年轻女性，声线清亮、有亲和力，语速自然偏轻快，像播客主持人一样放松但吐字清楚，适合知识讲解和日常介绍。",
    "元气少女": "元气少女音色，明亮、轻快、笑意明显，语速偏快，句尾灵动，适合轻松内容和年轻化短视频。",
    "甜系邻家女孩": "年轻女性，声音甜美、软萌、亲近，语速轻快，带一点黏人感和撒娇气质，但保持清晰可懂，适合轻松日常、聊天向内容。",
    "温柔女友感": "年轻女性，声音温柔、柔软、低饱和，语速偏慢，带轻微耳语感和亲密感，适合情感、治愈和晚间陪伴内容。",
    "ASMR 低语女声": "年轻女性，声音极度轻柔，像在耳边说话，呼吸感明显，语速慢，适合哄睡、放松和沉浸式内容。",
    "少女动漫感": "年轻女性，声音明亮但不过分夸张，带一点动漫感和元气感，语调起伏更明显，适合二次元风格内容和年轻化口播。",
    "古风说书人": "古风说书人音色，成熟、有韵味，语速从容，语调起伏带叙事感，适合历史、武侠和传统故事。",
    "小说旁白女声": "小说旁白音色，声音有画面感和沉浸感，情绪表达细腻，节奏有起伏，适合剧情、故事和角色独白。",
    "科技产品解说音色": "清晰、理性、现代，语速中等偏快，语气专业但不生硬，适合产品演示和技术说明。",
    "少年感男声": "年轻男性，声音干净明亮，有少年感，语速略快，语气轻松自然，适合短视频口播和产品介绍。",
    "低沉纪录片男声": "成熟男性，低沉稳重，气息稳定，语速中等偏慢，像纪录片旁白，带一点故事感但不过分夸张。",
    "电台夜谈男声": "电台夜谈男声，温暖、低缓、松弛，带轻微气声，语速偏慢，适合情感电台、睡前故事和长篇陪伴内容。",
    "悬疑旁白": "悬疑故事旁白，声线偏低，语速克制，停顿明显，带一点紧张感和神秘感，适合悬疑、案件和氛围叙述。",
}


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
    app.state.mimo_asr = MimoAsrService(settings)
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
            voice_design_templates=[
                {"name": name, "value": value}
                for name, value in VOICE_DESIGN_TEMPLATES.items()
            ],
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

        if payload.stream:
            return await _handle_stream_synthesis(service, payload)

        try:
            audio_bytes = await service.synthesize(payload)
        except MimoTtsError as exc:
            detail = str(exc)
            status_code = 400 if detail.startswith("不支持的预置音色") else 502
            raise HTTPException(status_code=status_code, detail=detail) from exc

        headers = service.build_download_headers()
        return Response(content=audio_bytes, media_type="audio/wav", headers=headers)

    @app.post(
        "/api/v1/speech/recognize",
        response_model=AsrResponse,
        responses={
            502: {"description": "上游 ASR 服务失败"},
        },
    )
    async def recognize(payload: AsrRequest) -> AsrResponse:
        service: MimoAsrService = app.state.mimo_asr

        try:
            result = await service.recognize(payload.audio_data, payload.language)
        except MimoAsrError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return AsrResponse.model_validate(result)

    async def _handle_stream_synthesis(
        service: MimoTtsService,
        payload: SynthesisRequest,
    ) -> StreamingResponse:
        async def event_generator():
            try:
                async for pcm_chunk in service.synthesize_stream(payload):
                    chunk_b64 = base64.b64encode(pcm_chunk).decode("ascii")
                    sse_data = json.dumps({"audio": chunk_b64})
                    yield f"data: {sse_data}\n\n"
                yield "data: [DONE]\n\n"
            except MimoTtsError as exc:
                error_data = json.dumps({"error": str(exc)})
                yield f"data: {error_data}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

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
                        resample_state = None
                        async for pcm_chunk_24k in service.synthesize_stream(payload):
                            pcm_chunk_16k, resample_state = audioop.ratecv(
                                pcm_chunk_24k,
                                2,
                                1,
                                service.STREAM_PCM16_SAMPLE_RATE,
                                16000,
                                resample_state,
                            )
                            await _send_bytes_safely(websocket, send_lock, pcm_chunk_16k)
                            await asyncio.sleep(0)
                    except (MimoTtsError, ValidationError) as exc:
                        await _send_text_safely(
                            websocket,
                            send_lock,
                            f"data=error message={exc}",
                        )
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
