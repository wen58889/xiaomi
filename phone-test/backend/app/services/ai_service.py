"""云端AI大模型调用服务。

在流程引擎中作为 ai_call 动作的后端，支持：
- 纯文本生成（无上下文）
- 带截图分析（视觉模型）
- 带OCR文本分析

复用 APIVisionAdapter 的 _chat 能力，支持 OpenAI / Anthropic / Custom / ModelScope。
"""
from __future__ import annotations

import asyncio
import logging
import re

from app.config import get_settings
from app.vision.api_vision import APIVisionAdapter

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_DELAY = 2
HARD_TIMEOUT = 120


def _clean_response(text: str) -> str:
    """清理AI回复：去除尾部分析括号、字数统计等元信息。"""
    text = text.strip()
    text = re.sub(r'\s*[（(][^）)]*[）)]\s*$', '', text)
    lines = text.split('\n')
    if len(lines) > 1:
        text = lines[0].strip()
    return text.strip()


async def ai_call(
    prompt: str,
    model: str = "",
    context_image: bytes | None = None,
    max_tokens: int = 512,
    temperature: float = 1.0,
) -> str:
    """调用云端AI大模型，带重试+硬超时保底。

    Args:
        prompt: 用户提示词
        model: 指定模型名称（留空则用配置中的默认模型）
        context_image: 截图bytes（提供则走视觉模型，None则纯文本）
        max_tokens: 最大生成token数
        temperature: 采样温度

    Returns:
        AI生成的文本（已清理元信息）
    """
    s = get_settings()

    provider = "custom" if s.custom_api_base_url else ("openai" if s.openai_api_key else "anthropic")
    adapter = APIVisionAdapter(provider=provider)

    if model:
        adapter.model = model

    full_prompt = f"{prompt}\n\n只返回内容本身，不要添加任何分析、解释、字数统计或括号备注。"
    images = [context_image] if context_image else []

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("ai_call attempt %d/%d: prompt=%s...", attempt, MAX_RETRIES, prompt[:60])
            result = await asyncio.wait_for(
                adapter._chat(full_prompt, images, max_tokens),
                timeout=HARD_TIMEOUT,
            )
            cleaned = _clean_response(result)
            logger.info("ai_call attempt %d OK: %s...", attempt, cleaned[:80])
            return cleaned
        except asyncio.TimeoutError:
            last_error = RuntimeError(f"AI请求超时（{HARD_TIMEOUT}秒硬超时）")
            logger.warning("ai_call attempt %d/%d hard timeout (%ds)", attempt, MAX_RETRIES, HARD_TIMEOUT)
        except Exception as e:
            last_error = e
            logger.warning("ai_call attempt %d/%d failed: %s", attempt, MAX_RETRIES, e)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY)

    raise last_error
