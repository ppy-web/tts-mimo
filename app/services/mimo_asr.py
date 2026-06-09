import json
from typing import Any

import httpx

from app.config import Settings
from app.schemas import AsrRequest


class MimoAsrError(Exception):
    """Raised when the upstream Xiaomi MiMo ASR service fails."""


class MimoAsrService:
    MODEL = "mimo-v2.5-asr"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport

    def build_payload(self, payload: AsrRequest) -> dict[str, Any]:
        return {
            "model": self.MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": payload.audio_data,
                            },
                        }
                    ],
                }
            ],
            "asr_options": {
                "language": payload.language,
            },
        }

    async def recognize(self, audio_data_url: str, language: str = "auto") -> dict[str, Any]:
        if not self.settings.has_api_key:
            raise MimoAsrError("未配置 MIMO_API_KEY。")

        payload = AsrRequest(audio_data=audio_data_url, language=language)
        request_body = self.build_payload(payload)
        timeout = httpx.Timeout(self.settings.mimo_timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
            try:
                response = await client.post(
                    self._build_request_url(),
                    headers=self._build_headers(),
                    json=request_body,
                )
            except httpx.TimeoutException as exc:
                raise MimoAsrError("请求小米语音识别服务超时。") from exc
            except httpx.HTTPError as exc:
                raise MimoAsrError("请求小米语音识别服务失败。") from exc

        if response.status_code >= 400:
            detail = self._extract_error_detail(response)
            raise MimoAsrError(f"小米语音识别服务返回错误: {detail}")

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise MimoAsrError("小米语音识别服务返回了无效的 JSON。") from exc

        return {
            "text": self.extract_text(data),
            "usage": data.get("usage") if isinstance(data.get("usage"), dict) else {},
        }

    def _build_headers(self) -> dict[str, str]:
        return {
            "api-key": self.settings.mimo_api_key,
            "Content-Type": "application/json",
        }

    def _build_request_url(self) -> str:
        base_url = self.settings.mimo_base_url.rstrip("/")
        return f"{base_url}/chat/completions"

    @staticmethod
    def extract_text(data: dict[str, Any]) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MimoAsrError("上游返回缺少识别文本。") from exc

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
            text = "".join(text_parts).strip()
            if text:
                return text

        raise MimoAsrError("上游返回的识别文本格式无法解析。")

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
