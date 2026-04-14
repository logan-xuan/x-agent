"""Speech-text rewriting for TTS preprocessing."""

from __future__ import annotations

from ...config.manager import get_config
from ...services.llm.provider import LLMResponse
from ...utils.logger import get_logger
from .text_normalizer import normalize_text_for_tts

logger = get_logger(__name__)

_REWRITE_SYSTEM_PROMPT = (
    "你是语音播报文案改写器。"
    "请把输入内容改写成适合中文 TTS 朗读的纯文本，不要输出 Markdown，不要输出 URL，"
    "不要解释规则，不要添加寒暄。"
    "保留原始事实、语气与重点。"
    "列表请改成自然短句。"
    "代码块或实现细节不适合朗读时，请简洁表达为“代码片段已省略”。"
    "只输出改写结果。"
)


def _get_llm_router():
    from ...main import get_llm_router

    return get_llm_router()


class SpeechTextRewriter:
    """Rewrite rich text into speech-friendly text before TTS synthesis."""

    async def rewrite(self, text: str, *, metadata: dict[str, object] | None = None) -> str:
        base_text = normalize_text_for_tts(text)
        mode = get_config().voice.rewrite.mode
        if mode != "model":
            return base_text

        try:
            router = _get_llm_router()
            response = await router.chat(
                [
                    {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                stream=False,
                session_id=str((metadata or {}).get("session_id") or ""),
            )
        except Exception as exc:
            logger.warning(
                "Voice speech rewrite model failed, falling back to rules mode",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "session_id": (metadata or {}).get("session_id"),
                },
            )
            return base_text

        candidate = _response_content(response).strip()
        if not candidate:
            return base_text

        normalized_candidate = normalize_text_for_tts(candidate)
        return normalized_candidate or base_text


def _response_content(response: object) -> str:
    if isinstance(response, LLMResponse):
        return response.content or ""
    return str(getattr(response, "content", "") or "")
