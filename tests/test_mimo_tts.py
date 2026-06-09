import base64
import io
import json
import wave

import httpx
import pytest
from fastapi.testclient import TestClient

import app.config as app_config
import app.main as app_main
from app.config import Settings
from app.main import create_app
from app.schemas import SynthesisMode, SynthesisRequest
from app.services.mimo_tts import MimoTtsError, MimoTtsService


def make_settings(**overrides) -> Settings:
    values = {
        "mimo_api_key": "test-key",
        "mimo_base_url": "https://api.xiaomimimo.com/v1",
        "mimo_timeout_seconds": 10,
        "app_host": "127.0.0.1",
        "app_port": 8000,
    }
    values.update(overrides)
    return Settings(**values)


def make_service(transport: httpx.AsyncBaseTransport | None = None, **settings_overrides) -> MimoTtsService:
    return MimoTtsService(make_settings(**settings_overrides), transport=transport)


def make_test_wav_bytes(
    *,
    sample_rate: int = 8000,
    channels: int = 1,
    sample_width: int = 2,
    frame_count: int = 400,
) -> bytes:
    frame = (1000).to_bytes(sample_width, byteorder="little", signed=True)
    payload = frame * frame_count * channels
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(payload)
    return buffer.getvalue()


def test_build_payload_for_preset_mode() -> None:
    service = make_service()
    payload = SynthesisRequest(
        mode=SynthesisMode.PRESET,
        text="你好，欢迎使用。",
        voice="冰糖",
        style_prompt="温柔自然，语速适中。",
    )

    request_body = service.build_payload(payload)

    assert request_body["model"] == "mimo-v2.5-tts"
    assert request_body["audio"] == {"format": "wav", "voice": "冰糖"}
    assert request_body["messages"][0] == {"role": "user", "content": "温柔自然，语速适中。"}
    assert request_body["messages"][1] == {"role": "assistant", "content": "你好，欢迎使用。"}


def test_build_payload_for_voice_design_mode() -> None:
    service = make_service()
    payload = SynthesisRequest(
        mode=SynthesisMode.VOICE_DESIGN,
        text="请收听今天的节目。",
        voice_design_prompt="年轻男声，明亮、清晰、节奏轻快。",
    )

    request_body = service.build_payload(payload)

    assert request_body["model"] == "mimo-v2.5-tts-voicedesign"
    assert request_body["audio"] == {"format": "wav"}
    assert request_body["messages"][0] == {"role": "user", "content": "年轻男声，明亮、清晰、节奏轻快。"}
    assert request_body["messages"][1] == {"role": "assistant", "content": "请收听今天的节目。"}


def test_build_payload_for_voice_clone_mode() -> None:
    service = make_service()
    sample = "data:audio/wav;base64,UklGRg=="
    payload = SynthesisRequest(
        mode=SynthesisMode.VOICE_CLONE,
        text="[笑]这是一段复刻音色测试。",
        voice_clone_audio=sample,
        style_prompt="自然、清晰，语速适中。",
    )

    request_body = service.build_payload(payload)

    assert request_body["model"] == "mimo-v2.5-tts-voiceclone"
    assert request_body["audio"] == {"format": "wav", "voice": sample}
    assert request_body["messages"][0] == {"role": "user", "content": "自然、清晰，语速适中。"}
    assert request_body["messages"][1] == {"role": "assistant", "content": "[笑]这是一段复刻音色测试。"}


def test_voice_clone_audio_requires_data_uri() -> None:
    with pytest.raises(ValueError, match="voice_clone_audio"):
        SynthesisRequest(
            mode=SynthesisMode.VOICE_CLONE,
            text="你好",
            voice_clone_audio="UklGRg==",
        )


def test_voice_clone_audio_normalizes_base64_whitespace() -> None:
    payload = SynthesisRequest(
        mode=SynthesisMode.VOICE_CLONE,
        text="你好",
        voice_clone_audio="data:audio/mp3;base64,UklG\nRg==",
    )

    assert payload.voice_clone_audio == "data:audio/mp3;base64,UklGRg=="


def test_decode_audio_bytes() -> None:
    raw_audio = b"fake-wav-bytes"
    upstream_payload = {
        "choices": [
            {
                "message": {
                    "audio": {
                        "data": base64.b64encode(raw_audio).decode("utf-8"),
                    }
                }
            }
        ]
    }

    assert MimoTtsService.decode_audio_bytes(upstream_payload) == raw_audio


def test_split_synthesis_text_prefers_sentence_boundary() -> None:
    text = "第一句内容比较长，需要保持完整。第二句继续测试，第三句收尾。"

    segments = MimoTtsService.split_synthesis_text(text, max_chars=20)

    assert segments == ["第一句内容比较长，需要保持完整。", "第二句继续测试，第三句收尾。"]


def test_split_synthesis_text_keeps_audio_tag_together() -> None:
    text = "今天的开场白会稍微长一点，[笑]然后这里需要保持标签完整。"

    segments = MimoTtsService.split_synthesis_text(text, max_chars=15)

    assert "".join(segments) == text
    assert all("[笑" not in segment or "[笑]" in segment for segment in segments)


def test_concatenate_wav_segments_adds_pause() -> None:
    first = make_test_wav_bytes(sample_rate=8000, channels=1, frame_count=400)
    second = make_test_wav_bytes(sample_rate=8000, channels=1, frame_count=400)

    combined = MimoTtsService.concatenate_wav_segments([first, second], pause_ms=250)

    with wave.open(io.BytesIO(combined), "rb") as wav_file:
        assert wav_file.getframerate() == 8000
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getnframes() == 2800


def test_build_download_headers() -> None:
    headers = MimoTtsService.build_download_headers()
    assert headers["Content-Disposition"] == 'attachment; filename="tts-output.wav"'
    assert headers["Cache-Control"] == "no-store"


def test_wav_to_pcm_s16le_mono_16k_converts_sample_rate() -> None:
    service = make_service()
    wav_bytes = make_test_wav_bytes(sample_rate=8000, channels=1, frame_count=400)

    pcm_bytes = service.wav_to_pcm_s16le_mono_16k(wav_bytes)

    assert len(pcm_bytes) == 1600


def test_wav_to_pcm_s16le_mono_16k_converts_stereo() -> None:
    service = make_service()
    wav_bytes = make_test_wav_bytes(sample_rate=16000, channels=2, frame_count=200)

    pcm_bytes = service.wav_to_pcm_s16le_mono_16k(wav_bytes)

    assert len(pcm_bytes) == 400


def test_iter_pcm_chunks_splits_by_duration() -> None:
    service = make_service()
    pcm_bytes = b"\x01\x02" * 4000

    chunks = list(service.iter_pcm_chunks(pcm_bytes, chunk_duration_ms=100))

    assert len(chunks) == 3
    assert len(chunks[0]) == 3200
    assert len(chunks[1]) == 3200
    assert len(chunks[2]) == 1600


def test_health_endpoint_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    app_config.get_settings.cache_clear()
    monkeypatch.setattr(app_main, "get_settings", lambda: make_settings(mimo_api_key=""))
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["has_api_key"] is False
    app_config.get_settings.cache_clear()


def test_voices_endpoint() -> None:
    app = create_app()
    app.state.settings = make_settings()
    app.state.mimo_tts = MimoTtsService(app.state.settings)

    with TestClient(app) as client:
        response = client.get("/api/v1/voices")

    assert response.status_code == 200
    data = response.json()
    assert data["modes"] == ["preset", "voice_design", "voice_clone"]
    assert any(item["value"] == "冰糖" for item in data["voices"])
    assert data["audio_tag_examples"]
    assert data["voice_design_templates"]


def test_synthesize_endpoint_validation_error() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/speech/synthesize",
            json={"mode": "preset", "text": "你好"},
        )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_synthesize_success_with_mock_transport() -> None:
    raw_audio = b"RIFFfakewav"

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api.xiaomimimo.com/v1/chat/completions")
        body = request.read().decode("utf-8")
        assert "mimo-v2.5-tts" in body
        assert "assistant" in body
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "audio": {
                                "data": base64.b64encode(raw_audio).decode("utf-8"),
                            }
                        }
                    }
                ]
            },
        )

    service = make_service(transport=httpx.MockTransport(handler))
    payload = SynthesisRequest(mode="preset", text="你好", voice="冰糖")

    result = await service.synthesize(payload)

    assert result == raw_audio


@pytest.mark.anyio
async def test_synthesize_splits_long_text_and_merges_wav_segments() -> None:
    requested_texts = []
    wav_bytes = make_test_wav_bytes(sample_rate=8000, channels=1, frame_count=400)

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        requested_texts.append(body["messages"][-1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "audio": {
                                "data": base64.b64encode(wav_bytes).decode("utf-8"),
                            }
                        }
                    }
                ]
            },
        )

    service = make_service(
        transport=httpx.MockTransport(handler),
        tts_segment_max_chars=50,
        tts_segment_pause_ms=250,
    )
    payload = SynthesisRequest(
        mode="preset",
        text=(
            "第一段内容比较长，需要完整保留语义和句号，避免被上游截断。"
            "第二段内容也比较长，需要独立请求后再合并，声音参数保持一致。"
            "第三段收尾，确认最终返回仍然是一个完整 WAV。"
        ),
        voice="冰糖",
    )

    result = await service.synthesize(payload)

    assert requested_texts == [
        "第一段内容比较长，需要完整保留语义和句号，避免被上游截断。",
        "第二段内容也比较长，需要独立请求后再合并，声音参数保持一致。",
        "第三段收尾，确认最终返回仍然是一个完整 WAV。",
    ]
    with wave.open(io.BytesIO(result), "rb") as wav_file:
        assert wav_file.getframerate() == 8000
        assert wav_file.getnframes() == 5200


@pytest.mark.anyio
async def test_synthesize_maps_upstream_error_to_exception() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    service = make_service(transport=httpx.MockTransport(handler))
    payload = SynthesisRequest(mode="preset", text="你好", voice="冰糖")

    with pytest.raises(MimoTtsError) as exc_info:
        await service.synthesize(payload)

    assert "invalid api key" in str(exc_info.value)


def test_websocket_synthesize_returns_pcm_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    pcm_data = b"\x01\x02\x03\x04" * 100  # some PCM data

    async def fake_synthesize_stream(self, payload: SynthesisRequest):
        assert payload.mode == SynthesisMode.PRESET
        assert payload.voice == "冰糖"
        assert payload.text == "你好，本地流式测试。"
        yield pcm_data

    app_config.get_settings.cache_clear()
    monkeypatch.setattr(app_main, "get_settings", lambda: make_settings())
    monkeypatch.setattr(MimoTtsService, "synthesize_stream", fake_synthesize_stream)
    app = create_app()

    with TestClient(app) as client:
        with client.websocket_connect("/virtualhuman/speech/synthesis/1103") as websocket:
            assert websocket.receive_text() == "connect-success"
            websocket.send_text("ping")
            assert websocket.receive_json() == {"type": "pong"}
            websocket.send_text("你好，本地流式测试。")

            audio_chunk = websocket.receive_bytes()
            assert audio_chunk

    app_config.get_settings.cache_clear()


def test_websocket_synthesize_accepts_voice_clone_json(monkeypatch: pytest.MonkeyPatch) -> None:
    pcm_data = b"\x01\x02\x03\x04" * 50
    sample = "data:audio/wav;base64,UklGRg=="

    async def fake_synthesize_stream(self, payload: SynthesisRequest):
        assert payload.mode == SynthesisMode.VOICE_CLONE
        assert payload.voice_clone_audio == sample
        assert payload.style_prompt == "自然清晰。"
        assert payload.text == "复刻音色测试。"
        yield pcm_data

    app_config.get_settings.cache_clear()
    monkeypatch.setattr(app_main, "get_settings", lambda: make_settings())
    monkeypatch.setattr(MimoTtsService, "synthesize_stream", fake_synthesize_stream)
    app = create_app()

    with TestClient(app) as client:
        with client.websocket_connect("/virtualhuman/speech/synthesis/1103") as websocket:
            assert websocket.receive_text() == "connect-success"
            websocket.send_text(
                json.dumps(
                    {
                        "text": "复刻音色测试。",
                        "mode": "voice_clone",
                        "voice_clone_audio": sample,
                        "style_prompt": "自然清晰。",
                    },
                    ensure_ascii=False,
                )
            )

            audio_chunk = websocket.receive_bytes()
            assert audio_chunk

    app_config.get_settings.cache_clear()


# ─── Streaming / SSE tests ─────────────────────────────────────────


def test_build_payload_stream_for_preset_mode() -> None:
    service = make_service()
    payload = SynthesisRequest(
        mode=SynthesisMode.PRESET,
        text="你好，欢迎使用。",
        voice="冰糖",
        style_prompt="温柔自然，语速适中。",
    )

    request_body = service.build_payload(payload, stream=True)

    assert request_body["model"] == "mimo-v2.5-tts"
    assert request_body["audio"] == {"format": "pcm16", "voice": "冰糖"}
    assert request_body["stream"] is True
    assert request_body["messages"][0] == {"role": "user", "content": "温柔自然，语速适中。"}
    assert request_body["messages"][1] == {"role": "assistant", "content": "你好，欢迎使用。"}


def test_build_payload_stream_for_voice_design_mode() -> None:
    service = make_service()
    payload = SynthesisRequest(
        mode=SynthesisMode.VOICE_DESIGN,
        text="请收听今天的节目。",
        voice_design_prompt="年轻男声，明亮、清晰、节奏轻快。",
    )

    request_body = service.build_payload(payload, stream=True)

    assert request_body["model"] == "mimo-v2.5-tts-voicedesign"
    assert request_body["audio"] == {"format": "pcm16"}
    assert request_body["stream"] is True


def test_build_payload_stream_for_voice_clone_mode() -> None:
    service = make_service()
    sample = "data:audio/wav;base64,UklGRg=="
    payload = SynthesisRequest(
        mode=SynthesisMode.VOICE_CLONE,
        text="复刻测试。",
        voice_clone_audio=sample,
    )

    request_body = service.build_payload(payload, stream=True)

    assert request_body["model"] == "mimo-v2.5-tts-voiceclone"
    assert request_body["audio"] == {"format": "pcm16", "voice": sample}
    assert request_body["stream"] is True


def test_build_payload_no_stream_has_no_stream_key() -> None:
    service = make_service()
    payload = SynthesisRequest(mode="preset", text="你好", voice="冰糖")

    request_body = service.build_payload(payload, stream=False)

    assert "stream" not in request_body
    assert request_body["audio"]["format"] == "wav"


def test_extract_stream_audio_data() -> None:
    pcm_b64 = base64.b64encode(b"\x01\x02\x03\x04").decode()
    chunk = {
        "choices": [
            {
                "delta": {
                    "audio": {"data": pcm_b64},
                }
            }
        ]
    }
    result = MimoTtsService._extract_stream_audio_data(chunk)
    assert result == pcm_b64


def test_extract_stream_audio_data_returns_none_for_missing() -> None:
    assert MimoTtsService._extract_stream_audio_data({}) is None
    assert MimoTtsService._extract_stream_audio_data({"choices": []}) is None
    assert MimoTtsService._extract_stream_audio_data(
        {"choices": [{"delta": {}}]}
    ) is None
    assert MimoTtsService._extract_stream_audio_data(
        {"choices": [{"delta": {"audio": None}}]}
    ) is None


def test_generate_silence_pcm() -> None:
    silence = MimoTtsService._generate_silence_pcm(100, sample_rate=24000)
    assert len(silence) == 24000 * 2 // 10  # 100ms at 24kHz, 16-bit
    assert silence == b"\x00" * len(silence)


def test_generate_silence_pcm_zero_returns_empty() -> None:
    assert MimoTtsService._generate_silence_pcm(0) == b""


def _make_sse_chunk(pcm_bytes: bytes) -> str:
    """Build a single SSE data line for a streaming audio chunk."""
    chunk = {"choices": [{"delta": {"audio": {"data": base64.b64encode(pcm_bytes).decode()}}}]}
    return "data: " + json.dumps(chunk)


@pytest.mark.anyio
async def test_synthesize_single_stream_yields_pcm_chunks() -> None:
    pcm_chunk_1 = b"\x01\x02\x03\x04"
    pcm_chunk_2 = b"\x05\x06\x07\x08"

    sse_body = "\n".join([
        _make_sse_chunk(pcm_chunk_1),
        "",
        _make_sse_chunk(pcm_chunk_2),
        "data: [DONE]",
    ]) + "\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        assert body["stream"] is True
        assert body["audio"]["format"] == "pcm16"
        return httpx.Response(
            200,
            text=sse_body,
            headers={"content-type": "text/event-stream"},
        )

    service = make_service(transport=httpx.MockTransport(handler))
    payload = SynthesisRequest(mode="preset", text="你好", voice="冰糖")

    chunks = []
    async for chunk in service._synthesize_single_stream(payload):
        chunks.append(chunk)

    assert chunks == [pcm_chunk_1, pcm_chunk_2]


@pytest.mark.anyio
async def test_synthesize_stream_yields_pcm_chunks() -> None:
    pcm_data = b"\x01\x02\x03\x04"
    sse_body = _make_sse_chunk(pcm_data) + "\ndata: [DONE]\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=sse_body,
            headers={"content-type": "text/event-stream"},
        )

    service = make_service(transport=httpx.MockTransport(handler))
    payload = SynthesisRequest(mode="preset", text="你好", voice="冰糖")

    chunks = []
    async for chunk in service.synthesize_stream(payload):
        chunks.append(chunk)

    assert chunks == [pcm_data]


@pytest.mark.anyio
async def test_synthesize_stream_inserts_silence_between_segments() -> None:
    pcm_data = b"\x01\x02\x03\x04"
    sse_body = _make_sse_chunk(pcm_data) + "\ndata: [DONE]\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=sse_body,
            headers={"content-type": "text/event-stream"},
        )

    service = make_service(
        transport=httpx.MockTransport(handler),
        tts_segment_max_chars=50,
        tts_segment_pause_ms=50,
    )
    payload = SynthesisRequest(
        mode="preset",
        text="第一段内容确实比较长，需要完整保留语义和句号才能被正确分段。第二段内容也确实比较长，需要独立请求后再合并为最终音频。",
        voice="冰糖",
    )

    chunks = []
    async for chunk in service.synthesize_stream(payload):
        chunks.append(chunk)

    # Should have: pcm_data + silence + pcm_data (2 segments with pause)
    assert len(chunks) == 3
    assert chunks[0] == pcm_data
    assert chunks[1] == MimoTtsService._generate_silence_pcm(50, sample_rate=24000)
    assert chunks[2] == pcm_data


def test_synthesis_request_stream_default_false() -> None:
    payload = SynthesisRequest(mode="preset", text="你好", voice="冰糖")
    assert payload.stream is False


def test_synthesis_request_stream_true() -> None:
    payload = SynthesisRequest(mode="preset", text="你好", voice="冰糖", stream=True)
    assert payload.stream is True


def test_sse_endpoint_returns_sse_events(monkeypatch: pytest.MonkeyPatch) -> None:
    pcm_data = b"\x01\x02\x03\x04"
    sse_body = _make_sse_chunk(pcm_data) + "\ndata: [DONE]\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=sse_body,
            headers={"content-type": "text/event-stream"},
        )

    mock_transport = httpx.MockTransport(handler)
    original_init = MimoTtsService.__init__

    def patched_init(self, settings, transport=None):
        original_init(self, settings, transport=mock_transport)

    app_config.get_settings.cache_clear()
    monkeypatch.setattr(app_main, "get_settings", lambda: make_settings())
    monkeypatch.setattr(MimoTtsService, "__init__", patched_init)
    app = create_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/speech/synthesize",
            json={"mode": "preset", "text": "你好", "voice": "冰糖", "stream": True},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    text = response.text
    assert "data:" in text
    assert "[DONE]" in text
    expected_b64 = base64.b64encode(pcm_data).decode()
    assert expected_b64 in text

    app_config.get_settings.cache_clear()


def test_websocket_synthesize_uses_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    pcm_chunk = b"\x01\x02\x03\x04" * 100  # some PCM data

    async def fake_synthesize_stream(self, payload: SynthesisRequest):
        assert payload.mode == SynthesisMode.PRESET
        assert payload.voice == "冰糖"
        assert payload.text == "你好，流式测试。"
        yield pcm_chunk

    app_config.get_settings.cache_clear()
    monkeypatch.setattr(app_main, "get_settings", lambda: make_settings())
    monkeypatch.setattr(MimoTtsService, "synthesize_stream", fake_synthesize_stream)
    app = create_app()

    with TestClient(app) as client:
        with client.websocket_connect("/virtualhuman/speech/synthesis/1103") as websocket:
            assert websocket.receive_text() == "connect-success"
            websocket.send_text("你好，流式测试。")

            audio_chunk = websocket.receive_bytes()
            assert audio_chunk
            # Should be resampled from 24kHz to 16kHz (roughly 2/3 the size)
            expected_len = round(len(pcm_chunk) * 16000 / 24000)
            # Allow small rounding tolerance from audioop.ratecv
            assert abs(len(audio_chunk) - expected_len) <= 4
            assert len(audio_chunk) > 0

    app_config.get_settings.cache_clear()