"""云端AI大模型调用服务。

在流程引擎中作为 ai_call 动作的后端，支持：
- 纯文本生成（无上下文）
- 带截图分析（视觉模型）
- 带OCR文本分析

复用 APIVisionAdapter 的 _chat 能力，支持 OpenAI / Anthropic / Custom / ModelScope。
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.vision.api_vision import APIVisionAdapter

logger = logging.getLogger(__name__)


async def ai_call(
    prompt: str,
    model: str = "",
    context_image: bytes | None = None,
    max_tokens: int = 512,
    temperature: float = 1.0,
) -> str:
    """调用云端AI大模型。

    Args:
        prompt: 用户提示词
        model: 指定模型名称（留空则用配置中的默认模型）
        context_image: 截图bytes（提供则走视觉模型，None则纯文本）
        max_tokens: 最大生成token数
        temperature: 采样温度

    Returns:
        AI生成的文本
    """
    s = get_settings()

    provider = "custom" if s.custom_api_base_url else ("openai" if s.openai_api_key else "anthropic")
    adapter = APIVisionAdapter(provider=provider)

    if model:
        adapter.model = model

    images = [context_image] if context_image else []
    result = await adapter._chat(prompt, images, max_tokens)
    logger.info("ai_call: prompt=%s... -> result=%s...", prompt[:50], result[:50])
    return result.strip()