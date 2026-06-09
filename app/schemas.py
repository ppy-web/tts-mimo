from enum import Enum

import base64
import re

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SynthesisMode(str, Enum):
    PRESET = "preset"
    VOICE_DESIGN = "voice_design"
    VOICE_CLONE = "voice_clone"


VOICE_CLONE_DATA_URI_PATTERN = re.compile(
    r"^data:(audio/(?:mpeg|mp3|wav));base64,([A-Za-z0-9+/=\s]+)$"
)
VOICE_CLONE_BASE64_MAX_BYTES = 10 * 1024 * 1024
ASR_AUDIO_DATA_URI_PATTERN = VOICE_CLONE_DATA_URI_PATTERN
ASR_AUDIO_BASE64_MAX_BYTES = 25 * 1024 * 1024


class VoiceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    value: str
    language: str
    gender: str
    note: str | None = None


class HealthResponse(BaseModel):
    status: str
    has_api_key: bool
    mimo_base_url: str


class VoiceDesignTemplateItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    value: str


class VoicesResponse(BaseModel):
    modes: list[str]
    voices: list[VoiceItem]
    audio_tag_examples: list[str] = Field(default_factory=list)
    voice_design_templates: list[VoiceDesignTemplateItem] = Field(default_factory=list)


class SynthesisRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    mode: SynthesisMode
    text: str = Field(min_length=1, max_length=10000)
    voice: str | None = None
    style_prompt: str | None = Field(default=None, max_length=2000)
    voice_design_prompt: str | None = Field(default=None, max_length=2000)
    voice_clone_audio: str | None = Field(
        default=None,
        description="音色复刻样本，格式为 data:audio/{mpeg|mp3|wav};base64,...",
    )
    stream: bool = Field(default=False, description="是否使用流式输出（SSE）")

    @field_validator("voice_clone_audio")
    @classmethod
    def validate_voice_clone_audio(cls, value: str | None) -> str | None:
        if value is None:
            return None

        match = VOICE_CLONE_DATA_URI_PATTERN.match(value)
        if match is None:
            raise ValueError(
                "voice_clone_audio 必须是 data:audio/mpeg;base64,...、"
                "data:audio/mp3;base64,... 或 data:audio/wav;base64,... 格式。"
            )

        base64_payload = re.sub(r"\s+", "", match.group(2))
        if len(base64_payload.encode("ascii")) > VOICE_CLONE_BASE64_MAX_BYTES:
            raise ValueError("voice_clone_audio 的 Base64 内容不能超过 10 MB。")

        try:
            base64.b64decode(base64_payload, validate=True)
        except ValueError as exc:
            raise ValueError("voice_clone_audio 包含无效的 Base64 内容。") from exc

        return f"data:{match.group(1)};base64,{base64_payload}"

    @model_validator(mode="after")
    def validate_by_mode(self) -> "SynthesisRequest":
        if self.mode == SynthesisMode.PRESET and not self.voice:
            raise ValueError("preset 模式必须提供 voice。")
        if self.mode == SynthesisMode.VOICE_DESIGN and not self.voice_design_prompt:
            raise ValueError("voice_design 模式必须提供 voice_design_prompt。")
        if self.mode == SynthesisMode.VOICE_CLONE and not self.voice_clone_audio:
            raise ValueError("voice_clone 模式必须提供 voice_clone_audio。")
        return self


class AsrRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    audio_data: str = Field(
        description="待识别音频，格式为 data:audio/{mpeg|mp3|wav};base64,...",
    )
    language: str = Field(default="auto", max_length=32)

    @field_validator("audio_data")
    @classmethod
    def validate_audio_data(cls, value: str) -> str:
        match = ASR_AUDIO_DATA_URI_PATTERN.match(value)
        if match is None:
            raise ValueError(
                "audio_data 必须是 data:audio/mpeg;base64,...、"
                "data:audio/mp3;base64,... 或 data:audio/wav;base64,... 格式。"
            )

        base64_payload = re.sub(r"\s+", "", match.group(2))
        if len(base64_payload.encode("ascii")) > ASR_AUDIO_BASE64_MAX_BYTES:
            raise ValueError("audio_data 的 Base64 内容不能超过 25 MB。")

        try:
            base64.b64decode(base64_payload, validate=True)
        except ValueError as exc:
            raise ValueError("audio_data 包含无效的 Base64 内容。") from exc

        return f"data:{match.group(1)};base64,{base64_payload}"

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        language = value.strip().lower() or "auto"
        allowed = {"auto", "zh", "en", "zh-cn", "zh_cn", "chinese", "english"}
        if language not in allowed:
            raise ValueError("language 仅支持 auto、zh 或 en。")
        if language in {"zh-cn", "zh_cn", "chinese"}:
            return "zh"
        if language == "english":
            return "en"
        return language


class AsrUsage(BaseModel):
    model_config = ConfigDict(extra="allow")

    seconds: float | None = None
    audio_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class AsrResponse(BaseModel):
    text: str
    usage: AsrUsage | dict[str, Any] = Field(default_factory=AsrUsage)
