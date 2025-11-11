from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.decision.llm_client import DeepSeekClient, Message, ToolCall


pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_async_openai(monkeypatch):
    mock_client = SimpleNamespace()
    mock_client.chat = SimpleNamespace()
    mock_client.chat.completions = SimpleNamespace()
    mock_client.chat.completions.create = AsyncMock()
    mock_client.embeddings = SimpleNamespace()
    mock_client.embeddings.create = AsyncMock()

    def _factory(**kwargs):  # noqa: D401
        return mock_client

    monkeypatch.setattr("src.decision.llm_client.AsyncOpenAI", _factory)
    return mock_client


async def test_deepseek_client_chat_parses_tool_calls(mock_async_openai):
    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(
            name="market_data_query",
            arguments='{"symbol": "BTC/USDT"}',
        ),
    )
    message = SimpleNamespace(content='{"regime": "bull"}', tool_calls=[tool_call])
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=SimpleNamespace(total_tokens=32),
        model="deepseek-chat",
    )

    mock_async_openai.chat.completions.create.return_value = response

    client = DeepSeekClient(api_key="test-key", model="deepseek-chat")
    result = await client.chat([Message(role="user", content="hi")])

    assert result.content == '{"regime": "bull"}'
    assert result.tool_calls is not None
    assert result.tool_calls[0].name == "market_data_query"
    assert result.tool_calls[0].arguments["symbol"] == "BTC/USDT"
    assert client.get_total_tokens() == 32


async def test_deepseek_client_embed_returns_vector(mock_async_openai):
    embedding_response = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
    )
    mock_async_openai.embeddings.create.return_value = embedding_response

    client = DeepSeekClient(api_key="test-key", model="deepseek-chat")
    vector = await client.embed("hello world")

    assert vector == [0.1, 0.2, 0.3]
    mock_async_openai.embeddings.create.assert_awaited()


async def test_message_to_dict_includes_tool_calls():
    message = Message(
        role="assistant",
        content=None,
        tool_calls=[ToolCall(id="1", name="tool", arguments={"a": 1})],
    )

    payload = message.to_dict()
    assert payload["tool_calls"][0]["function"]["name"] == "tool"
    assert payload["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
