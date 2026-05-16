"""
Shared pytest fixtures for DocSeer tests.

MockAsyncSession  — in-memory AsyncSession substitute
mock_agent        — BasicAgent with mocked prompt/model chain
mock_retriever    — Retriever stub returning []
test_app          — minimal FastAPI app with mocked state + overridden get_db
async_client      — httpx.AsyncClient wired to test_app
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.app.dependencies import get_db
from backend.app.models.paper import Paper, PaperStatus
from backend.app.routers import chat_router, papers_router, tasks_router


# ── MockAsyncSession ──────────────────────────────────────────────────────────


class MockResult:
    """Mimics the object returned by AsyncSession.execute()."""

    def __init__(self, rows: list[Any] | None = None):
        self._rows: list[Any] = rows or []

    def scalars(self) -> "MockResult":
        return self

    def all(self) -> list[Any]:
        return self._rows

    def scalar_one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None


class MockAsyncSession:
    """
    Minimal in-memory async SQLAlchemy session.

    Configuring execute() results per-test
    ───────────────────────────────────────
    Push results into _execute_queue before the request:

        mock_session.push_result(MockResult([paper]))   # first execute() call
        mock_session.push_result(MockResult([]))        # second call, etc.

    If the queue is empty, _execute_default is returned (MockResult([])).
    """

    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Any] = {}
        self._pending: list[Any] = []
        self._execute_queue: list[MockResult] = []
        self._execute_default: MockResult = MockResult()

    # ── queue helpers ─────────────────────────────────────────────────────────

    def push_result(self, result: MockResult) -> None:
        self._execute_queue.append(result)

    def set_default_result(self, result: MockResult) -> None:
        self._execute_default = result

    # ── session API ───────────────────────────────────────────────────────────

    def add(self, obj: Any) -> None:
        self._pending.append(obj)

    async def flush(self) -> None:
        for obj in self._pending:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            self._store[obj.id] = obj
        self._pending.clear()

    async def commit(self) -> None:
        for obj in self._pending:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            self._store[obj.id] = obj
        self._pending.clear()

    async def refresh(self, obj: Any) -> None:
        pass

    async def get(self, model: type, pk: Any) -> Any | None:
        return self._store.get(pk)

    async def execute(self, stmt: Any) -> MockResult:
        if self._execute_queue:
            return self._execute_queue.pop(0)
        return self._execute_default

    async def delete(self, obj: Any) -> None:
        self._store.pop(getattr(obj, "id", None), None)

    async def __aenter__(self) -> "MockAsyncSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


# ── agent / retriever mocks ───────────────────────────────────────────────────


@pytest.fixture
def mock_chain() -> MagicMock:
    """A mock LangChain chain whose astream yields two fake text chunks."""

    async def _astream(*args: Any, **kwargs: Any):
        for text in ("Hello ", "world."):
            chunk = MagicMock()
            chunk.content = text
            chunk.additional_kwargs = {}
            yield chunk

    async def _ainvoke(*args: Any, **kwargs: Any) -> MagicMock:
        msg = MagicMock()
        msg.content = "Hello world."
        msg.additional_kwargs = {}
        return msg

    chain = MagicMock()
    chain.astream = _astream
    chain.ainvoke = _ainvoke
    return chain


@pytest.fixture
def mock_agent(mock_chain: MagicMock) -> MagicMock:
    """BasicAgent substitute with a mocked prompt | model chain."""
    mock_llm = MagicMock()
    mock_llm.bind = MagicMock(return_value=mock_llm)

    mock_prompt = MagicMock()
    mock_prompt.__or__ = MagicMock(return_value=mock_chain)

    agent = MagicMock()
    agent.model = mock_llm
    agent.prompt = mock_prompt
    agent.chat_history = MagicMock()
    agent.chat_history.messages = []
    agent._update_chat_history = MagicMock()
    agent.clean_chat_history = MagicMock()
    return agent


@pytest.fixture
def mock_retriever() -> MagicMock:
    retriever = MagicMock()
    retriever.aretrieve = AsyncMock(return_value=[])
    return retriever


# ── session / app / client ────────────────────────────────────────────────────


@pytest.fixture
def mock_session() -> MockAsyncSession:
    return MockAsyncSession()


@pytest.fixture
def test_app(
    mock_session: MockAsyncSession,
    mock_agent: MagicMock,
    mock_retriever: MagicMock,
) -> FastAPI:
    """
    Minimal FastAPI app — real routers, no lifespan, mocked DB + state.
    """
    app = FastAPI()
    app.include_router(papers_router)
    app.include_router(chat_router)
    app.include_router(tasks_router)

    async def _override_db():
        yield mock_session

    app.dependency_overrides[get_db] = _override_db
    app.state.agent = mock_agent
    app.state.retriever = mock_retriever
    return app


@pytest.fixture
async def async_client(test_app: FastAPI) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client


# ── factory helpers ───────────────────────────────────────────────────────────


def make_paper(**kwargs: Any) -> Paper:
    """Return an in-memory Paper instance with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "title": "Test Paper",
        "authors": ["Alice", "Bob"],
        "year": 2024,
        "status": PaperStatus.metadata_only,
        "source_path": None,
        "date_added": __import__("datetime").datetime(
            2024, 1, 1, tzinfo=__import__("datetime").timezone.utc
        ),
    }
    defaults.update(kwargs)
    return Paper(**defaults)
