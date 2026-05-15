"""
Chat router
───────────
POST /chat/stream   – SSE stream; JSON events per chunk:
                      {"type": "thinking", "content": "..."}
                      {"type": "response", "content": "..."}
                      {"type": "done"}
POST /chat/invoke   – single blocking response
GET  /chat/history  – return full conversation history
DELETE /chat/history – clear conversation history
"""

from __future__ import annotations

import json
import logging
import asyncio
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from docseer.agents.utils import docs_to_md

from ..config import get_settings
from ..schemas.chat import ChatHistoryResponse, ChatMessage, QueryRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


# ── helpers ───────────────────────────────────────────────────────────────────


def _sse(payload: dict) -> str:
    """Format a single SSE event line."""
    return f"data: {json.dumps(payload)}\n\n"


def _build_context_md(query: str, context: list, settings) -> str:
    """Build a bounded context string to reduce first-token latency."""
    limited_context = context[: settings.chat_context_docs]
    context_md = docs_to_md(limited_context)
    if len(context_md) > settings.chat_max_context_chars:
        context_md = context_md[: settings.chat_max_context_chars]
        logger.debug(
            "Truncated chat context for query %r to %d chars",
            query,
            settings.chat_max_context_chars,
        )
    return context_md


async def _stream_chain(
    request: Request,
    query: str,
    think_mode: bool,
    paper_ids: list[str] | None = None,
) -> AsyncIterator[str]:
    """
    Core streaming coroutine.

    Yields raw SSE-formatted strings.  Handles both normal and think-mode
    responses; thinking tokens come in chunk.additional_kwargs["reasoning_content"].
    """
    agent = request.app.state.agent
    retriever = request.app.state.retriever
    settings = get_settings()

    # Flush headers immediately — client sees HTTP 200 + stream-start before
    # retrieval begins, so the connection is visible right away and benchmark
    # timing for retrieval is accurate.
    yield _sse({"type": "meta", "content": "stream-start"})

    context = []
    context_md = ""
    retrieval_error: str | None = None

    if settings.chat_fast_retrieval:
        try:
            context = await asyncio.wait_for(
                retriever.aretrieve(query, paper_ids=paper_ids),
                timeout=settings.chat_retrieval_timeout_seconds,
            )
            context_md = _build_context_md(query, context, settings)
        except Exception as exc:
            retrieval_error = str(exc)
            logger.warning(
                "Retriever failed for %r, continuing without context: %s",
                query,
                exc,
            )
    else:
        context = await retriever.aretrieve(query, paper_ids=paper_ids)
        context_md = _build_context_md(query, context, settings)

    if retrieval_error:
        yield _sse({"type": "meta", "content": "retrieval-unavailable"})

    # Always bind `reasoning` explicitly so Ollama knows to disable CoT when
    # think_mode=False.  langchain-ollama 1.0.1 maps `reasoning=True/False`
    # → `think=True/False` in the Ollama request AND sets the internal flag
    # that extracts reasoning_content from chunk.additional_kwargs.
    # Using bind(think=...) bypasses both — model thinks but content is lost.
    #
    # Note: num_predict is NOT overridden here.  Ollama applies num_predict
    # to response tokens only (not to the thinking block), so the default
    # 4096-token cap does not starve the response.  Passing num_predict via
    # .bind() would also fail — langchain-ollama passes bound kwargs as
    # top-level args to AsyncClient.chat(), but num_predict belongs inside
    # the options dict and is rejected as an unexpected keyword argument.
    llm = agent.model.bind(reasoning=think_mode)
    chain = agent.prompt | llm

    full_response = ""

    try:
        async for chunk in chain.astream(
            {
                "context": context_md,
                "question": query,
                "chat_history": agent.chat_history.messages[
                    -2 * settings.chat_history_turns :
                ],
            }
        ):
            # Thinking tokens (present only when think_mode is active and the
            # model supports reasoning — e.g. QwQ, deepseek-r1 via Ollama).
            # langchain-ollama 1.0.1 stores reasoning in "reasoning_content".
            thinking: str = (
                chunk.additional_kwargs.get("reasoning_content", "") or ""
            )
            if thinking:
                yield _sse({"type": "thinking", "content": thinking})

            # Regular response tokens
            text: str = chunk.content or ""
            if text:
                full_response += text
                yield _sse({"type": "response", "content": text})

    except Exception as exc:
        logger.exception("Streaming error for query %r: %s", query, exc)
        yield _sse({"type": "error", "content": str(exc)})
        return

    # Persist to shared history after the stream completes
    agent._update_chat_history(query, full_response)
    yield _sse({"type": "done"})


# ── endpoints ─────────────────────────────────────────────────────────────────


@router.post("/stream")
async def stream_chat(
    body: QueryRequest, request: Request
) -> StreamingResponse:
    """
    Server-Sent Events stream.

    Each event is a JSON object on a `data:` line, terminated by double
    newline.  Event types: thinking | response | done | error.
    """
    return StreamingResponse(
        _stream_chain(request, body.query, body.think_mode, body.paper_ids),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.post("/invoke")
async def invoke_chat(body: QueryRequest, request: Request) -> dict:
    """
    Blocking single-turn response (no streaming).

    Returns {"response": "<full answer>", "thinking": "<reasoning or null>"}.
    """
    agent = request.app.state.agent
    retriever = request.app.state.retriever
    settings = get_settings()

    if settings.chat_fast_retrieval:
        try:
            context = await asyncio.wait_for(
                retriever.aretrieve(body.query, paper_ids=body.paper_ids),
                timeout=settings.chat_retrieval_timeout_seconds,
            )
        except Exception as exc:
            logger.warning(
                "Retriever failed for invoke query %r, continuing without context: %s",
                body.query,
                exc,
            )
            context = []
    else:
        context = await retriever.aretrieve(
            body.query, paper_ids=body.paper_ids
        )
    context_md = _build_context_md(body.query, context, settings)

    llm = agent.model.bind(reasoning=True) if body.think_mode else agent.model
    chain = agent.prompt | llm

    result = await chain.ainvoke(
        {
            "context": context_md,
            "question": body.query,
            "chat_history": agent.chat_history.messages[
                -2 * settings.chat_history_turns :
            ],
        }
    )

    response_text: str = result.content or ""
    thinking_text: str = (
        result.additional_kwargs.get("reasoning_content") or None
    )

    agent._update_chat_history(body.query, response_text)

    return {"response": response_text, "thinking": thinking_text}


@router.get("/history", response_model=ChatHistoryResponse)
async def get_history(request: Request) -> ChatHistoryResponse:
    """Return the current in-process conversation history."""
    from langchain_core.messages import HumanMessage

    agent = request.app.state.agent
    messages = [
        ChatMessage(
            role="human" if isinstance(m, HumanMessage) else "ai",
            content=m.content,
        )
        for m in agent.chat_history.messages
    ]
    return ChatHistoryResponse(messages=messages)


@router.delete("/history", status_code=204)
async def clear_history(request: Request) -> None:
    """Wipe the conversation history kept in the agent."""
    request.app.state.agent.clean_chat_history()
