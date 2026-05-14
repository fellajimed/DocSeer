"""API tests for /chat router."""

from __future__ import annotations

import json


# ── POST /chat/stream ─────────────────────────────────────────────────────────


async def test_stream_returns_sse_events(async_client):
    resp = await async_client.post(
        "/chat/stream", json={"query": "What is RAG?", "think_mode": False}
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert "response" in types
    assert "done" in types


async def test_stream_response_content(async_client):
    resp = await async_client.post(
        "/chat/stream", json={"query": "Hello", "think_mode": False}
    )
    events = _parse_sse(resp.text)
    response_text = "".join(
        e["content"] for e in events if e["type"] == "response"
    )
    assert response_text == "Hello world."


async def test_stream_think_mode_binds_model(async_client, mock_agent):
    resp = await async_client.post(
        "/chat/stream", json={"query": "Think hard", "think_mode": True}
    )
    assert resp.status_code == 200
    mock_agent.model.bind.assert_called_once_with(think=True)


async def test_stream_no_think_mode_skips_bind(async_client, mock_agent):
    await async_client.post(
        "/chat/stream", json={"query": "No think", "think_mode": False}
    )
    mock_agent.model.bind.assert_not_called()


async def test_stream_thinking_events_emitted(async_client, mock_chain):
    """When a chunk has additional_kwargs['thinking'], a thinking event is emitted."""

    async def _astream_with_thinking(*args, **kwargs):
        think_chunk = _make_chunk(content="", thinking="Let me reason...")
        text_chunk = _make_chunk(content="Answer.", thinking="")
        yield think_chunk
        yield text_chunk

    mock_chain.astream = _astream_with_thinking

    resp = await async_client.post(
        "/chat/stream", json={"query": "Think?", "think_mode": True}
    )
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert "thinking" in types
    assert "response" in types


async def test_stream_updates_chat_history(async_client, mock_agent):
    await async_client.post(
        "/chat/stream", json={"query": "Remember this", "think_mode": False}
    )
    mock_agent._update_chat_history.assert_called_once_with(
        "Remember this", "Hello world."
    )


# ── POST /chat/invoke ─────────────────────────────────────────────────────────


async def test_invoke_returns_response(async_client):
    resp = await async_client.post(
        "/chat/invoke", json={"query": "What is 1+1?", "think_mode": False}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "Hello world."
    assert body["thinking"] is None


async def test_invoke_think_mode_binds_model(async_client, mock_agent):
    await async_client.post(
        "/chat/invoke", json={"query": "Deep question", "think_mode": True}
    )
    mock_agent.model.bind.assert_called_once_with(think=True)


async def test_invoke_updates_chat_history(async_client, mock_agent):
    await async_client.post(
        "/chat/invoke", json={"query": "Invoke me", "think_mode": False}
    )
    mock_agent._update_chat_history.assert_called_once_with(
        "Invoke me", "Hello world."
    )


# ── GET /chat/history ─────────────────────────────────────────────────────────


async def test_get_history_empty(async_client, mock_agent):
    mock_agent.chat_history.messages = []
    resp = await async_client.get("/chat/history")
    assert resp.status_code == 200
    assert resp.json() == {"messages": []}


async def test_get_history_with_messages(async_client, mock_agent):
    from langchain_core.messages import AIMessage, HumanMessage

    mock_agent.chat_history.messages = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there"),
    ]
    resp = await async_client.get("/chat/history")
    assert resp.status_code == 200
    msgs = resp.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0] == {"role": "human", "content": "Hello"}
    assert msgs[1] == {"role": "ai", "content": "Hi there"}


# ── DELETE /chat/history ──────────────────────────────────────────────────────


async def test_clear_history(async_client, mock_agent):
    resp = await async_client.delete("/chat/history")
    assert resp.status_code == 204
    mock_agent.clean_chat_history.assert_called_once()


# ── helpers ───────────────────────────────────────────────────────────────────


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE body into a list of JSON event dicts."""
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[len("data: ") :]))
            except json.JSONDecodeError:
                pass
    return events


def _make_chunk(content: str, thinking: str = "") -> object:
    from unittest.mock import MagicMock

    chunk = MagicMock()
    chunk.content = content
    chunk.additional_kwargs = {"thinking": thinking} if thinking else {}
    return chunk
