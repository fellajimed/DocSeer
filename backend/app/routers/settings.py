"""
Settings router
───────────────
GET  /models            – list all models available in Ollama
GET  /settings/models   – current LLM + embedding model names
POST /settings/models   – hot-swap LLM and/or embedding model (no restart needed)
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from langchain_ollama import ChatOllama, OllamaEmbeddings

from docseer.agents.basic_agent import BasicAgent
from docseer.databases.chroma import ChromaVectorDB
from docseer.retrievers.retriever import Retriever

from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["settings"])


# ── schemas ───────────────────────────────────────────────────────────────────


class ModelUpdate(BaseModel):
    llm_model: Optional[str] = None
    embedding_model: Optional[str] = None


class CurrentModels(BaseModel):
    llm_model: str
    embedding_model: str


# ── endpoints ─────────────────────────────────────────────────────────────────


@router.get("/models", response_model=list[str])
async def list_models() -> list[str]:
    """Return all model names currently available in Ollama."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        return sorted(m["name"] for m in data.get("models", []))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach Ollama at {settings.ollama_base_url}: {exc}",
        )


@router.get("/settings/models", response_model=CurrentModels)
async def get_current_models(request: Request) -> CurrentModels:
    """Return the currently active LLM and embedding model names."""
    agent: BasicAgent = request.app.state.agent
    retriever: Retriever = request.app.state.retriever
    return CurrentModels(
        llm_model=agent.model.model,
        embedding_model=retriever.vector_db.model_embeddings.model,
    )


@router.post("/settings/models", response_model=list[str])
async def update_models(body: ModelUpdate, request: Request) -> list[str]:
    """
    Hot-swap the LLM and/or embedding model on the running app.

    - LLM swap:       creates a new BasicAgent (with the current chat history
                      preserved) backed by the requested ChatOllama model.
    - Embedding swap: creates a new ChromaVectorDB with the requested
                      OllamaEmbeddings model and a new Retriever wrapping it.

    Returns a list of human-readable change strings, e.g.
      ["LLM → llama3.2:3b", "Embedding → nomic-embed-text"]
    or an empty list if nothing changed.
    """
    settings = get_settings()
    agent: BasicAgent = request.app.state.agent
    retriever: Retriever = request.app.state.retriever

    changes: list[str] = []

    # ── LLM hot-swap ─────────────────────────────────────────────────────────
    if body.llm_model and body.llm_model != agent.model.model:
        new_llm = ChatOllama(
            model=body.llm_model,
            base_url=settings.ollama_base_url,
            keep_alive=settings.chat_model_keep_alive,
            temperature=settings.chat_temperature,
            num_ctx=settings.chat_num_ctx,
            num_predict=settings.chat_num_predict,
        )
        new_agent = BasicAgent(
            llm_model=new_llm,
            max_turns=settings.chat_history_turns,
        )
        # Preserve in-memory chat history across the swap
        new_agent.chat_history = agent.chat_history

        request.app.state.agent = new_agent
        changes.append(f"LLM → {body.llm_model}")
        logger.info("LLM hot-swapped to %s", body.llm_model)

    # ── Embedding hot-swap ────────────────────────────────────────────────────
    if (
        body.embedding_model
        and body.embedding_model != retriever.vector_db.model_embeddings.model
    ):
        new_embeddings = OllamaEmbeddings(
            model=body.embedding_model,
            base_url=settings.ollama_base_url,
        )
        new_vector_db = ChromaVectorDB(
            model_embeddings=new_embeddings,
            batch_size=settings.embedding_batch_size,
            chroma_host=settings.chroma_host,
            chroma_port=settings.chroma_port,
        )
        new_retriever = Retriever(
            vector_db=new_vector_db,
            docstore=retriever.docstore,
            topk=settings.retriever_topk,
        )
        request.app.state.retriever = new_retriever
        changes.append(f"Embedding → {body.embedding_model}")
        logger.info("Embedding model hot-swapped to %s", body.embedding_model)

    return changes
