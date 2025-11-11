from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from unittest.mock import AsyncMock

from src.memory.long_term import QdrantLongTermMemory
from src.models.memory import MemoryQuery, TradingExperience


pytestmark = pytest.mark.asyncio


def _make_experience(exp_id: str) -> TradingExperience:
    now = datetime.now(timezone.utc)
    return TradingExperience(
        id=exp_id,
        timestamp=int(now.timestamp() * 1000),
        dt=now,
        situation="High volatility breakout",
        situation_embedding=[0.1, 0.2, 0.3],
        decision="Reduce exposure",
        decision_reasoning="Volatility spike",
        outcome="success",
        pnl=Decimal("150"),
        pnl_percentage=Decimal("3.5"),
        reflection="",
        lessons_learned=["Manage risk"],
        tags=["risk"],
        importance_score=0.8,
    )


def _make_payload(exp: TradingExperience) -> Dict[str, Any]:
    return {
        "id": exp.id,
        "timestamp": exp.timestamp,
        "datetime": exp.dt.isoformat(),
        "situation": exp.situation,
        "decision": exp.decision,
        "decision_reasoning": exp.decision_reasoning,
        "outcome": exp.outcome,
        "pnl": float(exp.pnl),
        "pnl_percentage": float(exp.pnl_percentage),
        "reflection": exp.reflection,
        "lessons_learned": exp.lessons_learned,
        "tags": exp.tags,
        "importance_score": exp.importance_score,
    }


@pytest.fixture
def memory(monkeypatch):
    mem = QdrantLongTermMemory(qdrant_url="http://test")
    mem.qdrant = AsyncMock()
    mem.openai = None
    monkeypatch.setattr(mem, "_generate_embedding", AsyncMock(return_value=[0.1, 0.2, 0.3]))
    return mem


async def test_store_experience_uses_existing_embedding(memory):
    experience = _make_experience("exp-1")
    await memory.store_experience(experience)

    memory.qdrant.upsert.assert_awaited_once()
    args, kwargs = memory.qdrant.upsert.await_args
    assert kwargs["collection_name"] == memory.COLLECTION_NAME
    point = kwargs["points"][0]
    assert point.payload["decision"] == "Reduce exposure"


async def test_search_similar_experiences_returns_models(memory, monkeypatch):
    experience = _make_experience("exp-2")
    payload = _make_payload(experience)
    memory.qdrant.search.return_value = [SimpleNamespace(payload=payload)]

    query = MemoryQuery(query_text="volatility", query_embedding=[0.2, 0.1], top_k=1)
    results = await memory.search_similar_experiences(query)

    assert len(results) == 1
    assert results[0].decision == "Reduce exposure"
    memory.qdrant.search.assert_awaited_once()


async def test_update_experience_calls_set_payload(memory):
    memory.qdrant.set_payload.return_value = True
    result = await memory.update_experience("exp-3", {"outcome": "failure"})

    assert result is True
    memory.qdrant.set_payload.assert_awaited_once()


async def test_get_experience_by_id_returns_instance(memory):
    experience = _make_experience("exp-4")
    payload = _make_payload(experience)
    memory.qdrant.retrieve.return_value = [SimpleNamespace(payload=payload)]

    fetched = await memory.get_experience_by_id("exp-4")

    assert fetched is not None
    assert fetched.id == "exp-4"
    memory.qdrant.retrieve.assert_awaited_once()


async def test_get_experience_by_id_returns_none(memory):
    memory.qdrant.retrieve.return_value = []
    fetched = await memory.get_experience_by_id("not-found")

    assert fetched is None
