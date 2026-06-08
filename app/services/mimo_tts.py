import base64
import audioop
import json
import wave
from io import BytesIO
from pathlib import Path
from typing import Any, Iterator

import httpx

from app.config import Settings
from app.schemas import SynthesisMode, SynthesisRequest, VoiceItem


class MimoTtsError(Exception):
    """Raised when the upstream Xiaomi MiMo TTS service fails."""


class MimoTtsService:
    PRESET_MODEL = "mimo-v2.5-tts"
    VOICE_DESIGN_MODEL = "mimo-v2.5-tts-voicedesign"
    VOICE_CLONE_MODEL = "mimo-v2.5-tts-voiceclone"
    STRONG_TEXT_BOUNDARIES = "。！？!?；;\n"
    SOFT_TEXT_BOUNDARIES = "，,、：: "
    CLOSING_QUOTES = "\"'”’）)]】》"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._voices = self._load_voices(settings.voices_path)
        self._voice_values = {voice.value for voice in self._voices}

    @property
    def voices(self) -> list[VoiceItem]:
        return self._voices

    def ensure_valid_voice(self, voice: str) -> None:
        if voice not in self._voice_values:
            raise MimoTtsError(f"不支持的预置音色: {voice}")

    def build_payload(self, payload: SynthesisRequest) -> dict[str, Any]:
        if payload.mode == SynthesisMode.PRESET:
            if payload.voice is None:
                raise MimoTtsError("preset 模式缺少 voice。")
            self.ensure_valid_voice(payload.voice)
            messages: list[dict[str, str]] = []
            if payload.style_prompt:
                messages.append({"role": "user", "content": payload.style_prompt})
            messages.append({"role": "assistant", "content": payload.text})
            return {
                "model": self.PRESET_MODEL,
                "messages": messages,
                "audio": {"format": "wav", "voice": payload.voice},
            }

        if payload.mode == SynthesisMode.VOICE_DESIGN:
            if payload.voice_design_prompt is None:
                raise MimoTtsError("voice_design 模式缺少 voice_design_prompt。")
            return {
                "model": self.VOICE_DESIGN_MODEL,
                "messages": [
                    {"role": "user", "content": payload.voice_design_prompt},
                    {"role": "assistant", "content": payload.text},
                ],
                "audio": {"format": "wav"},
            }

        if payload.mode != SynthesisMode.VOICE_CLONE:
            raise MimoTtsError(f"不支持的合成模式: {payload.mode}")
        if payload.voice_clone_audio is None:
            raise MimoTtsError("voice_clone 模式缺少 voice_clone_audio。")
        messages = []
        if payload.style_prompt:
            messages.append({"role": "user", "content": payload.style_prompt})
        messages.append({"role": "assistant", "content": payload.text})
        return {
            "model": self.VOICE_CLONE_MODEL,
            "messages": messages,
            "audio": {"format": "wav", "voice": payload.voice_clone_audio},
        }

    async def synthesize(self, payload: SynthesisRequest) -> bytes:
        if not self.settings.has_api_key:
            raise MimoTtsError("未配置 MIMO_API_KEY。")

        text_segments = self.split_synthesis_text(
            payload.text,
            self.settings.tts_segment_max_chars,
        )
        if len(text_segments) <= 1:
            return await self._synthesize_single(payload)

        wav_segments = []
        for text_segment in text_segments:
            segment_payload = payload.model_copy(update={"text": text_segment})
            wav_segments.append(await self._synthesize_single(segment_payload))

        return self.concatenate_wav_segments(
            wav_segments,
            pause_ms=self.settings.tts_segment_pause_ms,
        )

    async def _synthesize_single(self, payload: SynthesisRequest) -> bytes:
        request_body = self.build_payload(payload)
        base_url = self.settings.mimo_base_url.rstrip("/")
        url = f"{base_url}/chat/completions"

        headers = {
            "api-key": self.settings.mimo_api_key,
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(self.settings.mimo_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
            try:
                response = await client.post(url, headers=headers, json=request_body)
            except httpx.TimeoutException as exc:
                raise MimoTtsError("请求小米语音服务超时。") from exc
            except httpx.HTTPError as exc:
                raise MimoTtsError("请求小米语音服务失败。") from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response)
            raise MimoTtsError(f"小米语音服务返回错误: {detail}")

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise MimoTtsError("小米语音服务返回了无效的 JSON。") from exc

        return self.decode_audio_bytes(data)

    @classmethod
    def split_synthesis_text(cls, text: str, max_chars: int) -> list[str]:
        normalized_text = text.strip()
        if len(normalized_text) <= max_chars:
            return [normalized_text] if normalized_text else []

        segments = []
        remaining = normalized_text
        while len(remaining) > max_chars:
            split_at = cls._choose_text_split_index(remaining, max_chars)
            split_at = cls._avoid_splitting_audio_tag(remaining, split_at, max_chars)

            segment = remaining[:split_at].strip()
            if segment:
                segments.append(segment)
            remaining = remaining[split_at:].strip()

        if remaining:
            segments.append(remaining)

        return segments

    @classmethod
    def _choose_text_split_index(cls, text: str, max_chars: int) -> int:
        search_area = text[: max_chars + 1]
        min_split_at = max(1, int(max_chars * 0.45))

        for boundaries in (cls.STRONG_TEXT_BOUNDARIES, cls.SOFT_TEXT_BOUNDARIES):
            split_at = cls._find_last_boundary(search_area, boundaries)
            if split_at >= min_split_at:
                return cls._include_closing_quotes(text, split_at, max_chars)

        return max_chars

    @staticmethod
    def _find_last_boundary(text: str, boundaries: str) -> int:
        best = 0
        for boundary in boundaries:
            boundary_at = text.rfind(boundary)
            if boundary_at >= 0:
                best = max(best, boundary_at + 1)
        return best

    @classmethod
    def _include_closing_quotes(cls, text: str, split_at: int, max_chars: int) -> int:
        while (
            split_at < len(text)
            and split_at < max_chars + 8
            and text[split_at] in cls.CLOSING_QUOTES
        ):
            split_at += 1
        return split_at

    @staticmethod
    def _avoid_splitting_audio_tag(text: str, split_at: int, max_chars: int) -> int:
        tag_pairs = (("[", "]"), ("(", ")"), ("（", "）"))
        for open_tag, close_tag in tag_pairs:
            open_at = text.rfind(open_tag, 0, split_at)
            close_at = text.rfind(close_tag, 0, split_at)
            if open_at <= close_at:
                continue

            close_after = text.find(close_tag, split_at)
            if close_after != -1 and close_after + 1 <= max_chars + 20:
                return close_after + 1
            if open_at > 0:
                return open_at

        return split_at

    @classmethod
    def concatenate_wav_segments(cls, wav_segments: list[bytes], pause_ms: int = 250) -> bytes:
        if not wav_segments:
            raise MimoTtsError("没有可合并的音频片段。")
        if len(wav_segments) == 1:
            return wav_segments[0]

        decoded_segments = [cls._read_wav_segment(item) for item in wav_segments]
        first_params = decoded_segments[0][0]
        if all(params == first_params for params, _ in decoded_segments):
            return cls._write_wav_segments(decoded_segments, first_params, pause_ms)

        normalized_segments = [
            (
                (1, 2, 16000),
                cls.wav_to_pcm_s16le_mono_16k(wav_segment),
            )
            for wav_segment in wav_segments
        ]
        return cls._write_wav_segments(normalized_segments, (1, 2, 16000), pause_ms)

    @staticmethod
    def _read_wav_segment(wav_bytes: bytes) -> tuple[tuple[int, int, int], bytes]:
        try:
            with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                frame_rate = wav_file.getframerate()
                comp_type = wav_file.getcomptype()
                frame_count = wav_file.getnframes()
                pcm_bytes = wav_file.readframes(frame_count)
        except (wave.Error, EOFError) as exc:
            raise MimoTtsError("上游返回的 WAV 音频无法解析。") from exc

        if comp_type != "NONE":
            raise MimoTtsError("当前仅支持未压缩 WAV 音频。")

        return (channels, sample_width, frame_rate), pcm_bytes

    @staticmethod
    def _write_wav_segments(
        decoded_segments: list[tuple[tuple[int, int, int], bytes]],
        wav_params: tuple[int, int, int],
        pause_ms: int,
    ) -> bytes:
        channels, sample_width, frame_rate = wav_params
        pause_frames = round(frame_rate * pause_ms / 1000)
        pause_bytes = b"\x00" * pause_frames * channels * sample_width

        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(frame_rate)
            for index, (_, pcm_bytes) in enumerate(decoded_segments):
                if index > 0 and pause_bytes:
                    wav_file.writeframes(pause_bytes)
                wav_file.writeframes(pcm_bytes)

        return buffer.getvalue()

    @staticmethod
    def decode_audio_bytes(data: dict[str, Any]) -> bytes:
        try:
            audio_data = data["choices"][0]["message"]["audio"]["data"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MimoTtsError("上游返回缺少音频数据。") from exc

        try:
            return base64.b64decode(audio_data)
        except (ValueError, TypeError) as exc:
            raise MimoTtsError("上游音频数据解码失败。") from exc

    @staticmethod
    def build_download_headers(filename: str = "tts-output.wav") -> dict[str, str]:
        return {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        }

    @staticmethod
    def wav_to_pcm_s16le_mono_16k(wav_bytes: bytes) -> bytes:
        try:
            with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                frame_rate = wav_file.getframerate()
                comp_type = wav_file.getcomptype()
                frame_count = wav_file.getnframes()
                pcm_bytes = wav_file.readframes(frame_count)
        except (wave.Error, EOFError) as exc:
            raise MimoTtsError("上游返回的 WAV 音频无法解析。") from exc

        if comp_type != "NONE":
            raise MimoTtsError("当前仅支持未压缩 WAV 音频。")

        if channels == 2:
            pcm_bytes = audioop.tomono(pcm_bytes, sample_width, 0.5, 0.5)
            channels = 1
        elif channels != 1:
            raise MimoTtsError(f"暂不支持 {channels} 声道的 WAV 音频。")

        if sample_width != 2:
            pcm_bytes = audioop.lin2lin(pcm_bytes, sample_width, 2)
            sample_width = 2

        if frame_rate != 16000:
            pcm_bytes, _ = audioop.ratecv(
                pcm_bytes,
                sample_width,
                channels,
                frame_rate,
                16000,
                None,
            )
            expected_frame_count = round(frame_count * 16000 / frame_rate)
            expected_byte_length = expected_frame_count * sample_width
            if len(pcm_bytes) < expected_byte_length:
                pcm_bytes = pcm_bytes.ljust(expected_byte_length, b"\x00")
            elif len(pcm_bytes) > expected_byte_length:
                pcm_bytes = pcm_bytes[:expected_byte_length]

        return pcm_bytes

    @staticmethod
    def iter_pcm_chunks(
        pcm_bytes: bytes,
        chunk_duration_ms: int = 120,
        sample_rate: int = 16000,
        sample_width: int = 2,
    ) -> Iterator[bytes]:
        if not pcm_bytes:
            return

        chunk_size = max(
            sample_width,
            (sample_rate * sample_width * chunk_duration_ms // 1000),
        )
        if chunk_size % sample_width:
            chunk_size += sample_width - (chunk_size % sample_width)

        for start in range(0, len(pcm_bytes), chunk_size):
            yield pcm_bytes[start : start + chunk_size]

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            text = response.text.strip()
            return text or f"HTTP {response.status_code}"

        if isinstance(payload, dict):
            if isinstance(payload.get("error"), dict):
                message = payload["error"].get("message")
                if message:
                    return str(message)
            detail = payload.get("detail")
            if detail:
                return str(detail)
            message = payload.get("message")
            if message:
                return str(message)
        return f"HTTP {response.status_code}"

    @staticmethod
    def _load_voices(path: Path) -> list[VoiceItem]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [VoiceItem.model_validate(item) for item in raw]
