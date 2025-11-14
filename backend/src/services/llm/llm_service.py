"""
LLM Client Implementations

Provides asynchronous clients for DeepSeek and OpenAI compatible models.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx
from openai import (
    AsyncOpenAI,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    BadRequestError,
    RateLimitError as OpenAIRateLimitError,
)
from pydantic import BaseModel, ConfigDict, Field

from src.core.exceptions import EmbeddingError, LLMError, RateLimitError, TokenLimitError
from src.core.logger import get_logger


logger = get_logger(__name__)


def _safe_json_loads(payload: str | Dict[str, Any]) -> Dict[str, Any]:
    """Parse JSON string into a dictionary with graceful fallback."""
    if isinstance(payload, dict):
        return payload

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"raw": payload}


def _json_dumps(data: Any) -> str:
    """Serialize data to JSON string with Decimal support."""
    try:
        return json.dumps(data, default=str)
    except TypeError:
        return json.dumps({"raw": str(data)})


class ToolCall(BaseModel):
    """Structured representation of an LLM function/tool call."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Tool call identifier")
    name: str = Field(..., description="Registered tool name")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Call arguments")


class Message(BaseModel):
    """Generic chat message used by OpenAI compatible APIs."""

    role: str = Field(..., description="Message role: system/user/assistant/tool")
    content: Optional[str] = Field(None, description="Message body")
    name: Optional[str] = Field(None, description="Function name for tool messages")
    tool_call_id: Optional[str] = Field(None, description="Tool call identifier for tool responses")
    tool_calls: Optional[List[ToolCall]] = Field(None, description="Tool calls issued by assistant")

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to OpenAI compatible dict."""
        message: Dict[str, Any] = {"role": self.role}

        if self.content is not None:
            message["content"] = self.content
        if self.name:
            message["name"] = self.name
        if self.tool_call_id:
            message["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": _json_dumps(call.arguments),
                    },
                }
                for call in self.tool_calls
            ]

        return message


class LLMResponse(BaseModel):
    """Normalized LLM response."""

    content: Optional[str] = Field(None, description="Assistant response content")
    tool_calls: Optional[List[ToolCall]] = Field(None, description="Function/tool calls to execute")
    finish_reason: str = Field(..., description="Finish reason provided by provider")
    tokens_used: int = Field(0, description="Total tokens used by the request")
    model: Optional[str] = Field(None, description="Model identifier used for the completion")


class _BaseLLMClient:
    """Shared implementation for OpenAI compatible async clients."""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        *,
        embedding_model: Optional[str] = None,
        max_retries: int = 2,
        retry_delay: float = 1.5,
    ) -> None:
        self._client = client
        self.model = model
        self.embedding_model = embedding_model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.total_tokens = 0
        self._logger = get_logger(self.__class__.__name__)

    async def chat(
        self,
        messages: List[Message],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> LLMResponse:
        """
        Execute a chat completion with automatic retry and error handling.

        Args:
            messages: Conversation history
            tools: Optional tool definitions (OpenAI function calling schema)
            temperature: Sampling temperature
            max_tokens: Maximum tokens for completion
        """
        payload = [msg.to_dict() for msg in messages]
        params: Dict[str, Any] = {
            "model": self.model,
            "messages": payload,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        attempt = 0
        last_error: Optional[Exception] = None

        while attempt <= self.max_retries:
            try:
                response = await self._client.chat.completions.create(**params)
                choice = response.choices[0]

                tool_calls: Optional[List[ToolCall]] = None
                if choice.message.tool_calls:
                    tool_calls = [
                        ToolCall(
                            id=tool_call.id,
                            name=tool_call.function.name,
                            arguments=_safe_json_loads(tool_call.function.arguments or "{}"),
                        )
                        for tool_call in choice.message.tool_calls
                    ]

                tokens_used = getattr(response.usage, "total_tokens", 0) or 0
                self.total_tokens += tokens_used

                # 获取API返回的模型名称,如果没有则使用配置的模型名称
                response_model = getattr(response, "model", self.model)

                # 添加调试日志
                if response_model != self.model:
                    self._logger.warning(
                        f"API返回的模型 '{response_model}' 与配置的模型 '{self.model}' 不一致,使用配置的模型名称"
                    )
                    response_model = self.model

                return LLMResponse(
                    content=choice.message.content,
                    tool_calls=tool_calls,
                    finish_reason=choice.finish_reason or "",
                    tokens_used=tokens_used,
                    model=response_model,
                )
            except OpenAIRateLimitError as exc:
                last_error = exc
                self._logger.warning("Rate limit encountered; retrying (%s/%s)", attempt + 1, self.max_retries)
                if attempt >= self.max_retries:
                    raise RateLimitError(
                        message="LLM rate limit exceeded",
                        details={"model": self.model},
                        original_exception=exc,
                    )
                await asyncio.sleep(self.retry_delay * (attempt + 1))
            except BadRequestError as exc:
                raise TokenLimitError(
                    message="LLM request rejected (bad request)",
                    details={"model": self.model},
                    original_exception=exc,
                ) from exc
            except (APITimeoutError, APIConnectionError, APIStatusError, httpx.HTTPError) as exc:
                last_error = exc
                self._logger.warning("Transient LLM error; retrying (%s/%s)", attempt + 1, self.max_retries)
                if attempt >= self.max_retries:
                    raise LLMError(
                        message="Failed to reach LLM service",
                        details={"model": self.model},
                        original_exception=exc,
                    )
                await asyncio.sleep(self.retry_delay * (attempt + 1))
            except Exception as exc:  # pylint: disable=broad-except
                raise LLMError(
                    message="Unexpected LLM failure",
                    details={"model": self.model},
                    original_exception=exc,
                ) from exc
            finally:
                attempt += 1

        raise LLMError(
            message="LLM request failed after retries",
            details={"model": self.model},
            original_exception=last_error,
        )

    async def embed(self, text: str) -> List[float]:
        """
        Generate embedding for the provided text.

        Args:
            text: Input text to embed
        """
        if not self.embedding_model:
            raise EmbeddingError(
                message="Embedding model not configured for client",
                details={"model": self.model},
            )

        try:
            response = await self._client.embeddings.create(
                model=self.embedding_model,
                input=text,
            )
            embedding = response.data[0].embedding
            return list(embedding)  # ensure concrete list
        except Exception as exc:  # pylint: disable=broad-except
            raise EmbeddingError(
                message="Failed to generate embedding",
                details={"model": self.embedding_model, "text_length": len(text)},
                original_exception=exc,
            ) from exc

    def get_total_tokens(self) -> int:
        """Return cumulative token usage for this client."""
        return self.total_tokens


class DeepSeekClient(_BaseLLMClient):
    """Async client for DeepSeek models (OpenAI compatible API)."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        timeout: int = 60,
        embedding_model: Optional[str] = "text-embedding-3-small",
        max_retries: int = 2,
        retry_delay: float = 1.5,
    ) -> None:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        super().__init__(
            client,
            model=model,
            embedding_model=embedding_model,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )


class QwenClient(_BaseLLMClient):
    """Async client for Qwen (千问) models (OpenAI compatible API)."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: str = "qwen-plus",
        timeout: int = 60,
        embedding_model: Optional[str] = None,
        max_retries: int = 2,
        retry_delay: float = 1.5,
    ) -> None:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        super().__init__(
            client,
            model=model,
            embedding_model=embedding_model,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        # 添加日志显示正在使用的模型
        logger.info(f"🤖 初始化千问模型客户端: {model} (base_url={base_url})")


class OpenAIClient(_BaseLLMClient):
    """Async client for OpenAI models."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4-0613",
        embedding_model: str = "text-embedding-3-small",
        timeout: int = 60,
        max_retries: int = 2,
        retry_delay: float = 1.5,
    ) -> None:
        client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        super().__init__(
            client,
            model=model,
            embedding_model=embedding_model,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
