"""
Unified FastAPI application
───────────────────────────
Lifespan:
  • Runs Alembic migrations to HEAD (safe to run on every restart)
  • Initialises shared Retriever + BasicAgent stored in app.state
  • Disposes the async engine on shutdown

Routers:
  /papers  – paper registry CRUD + import + ingest dispatch
  /chat    – SSE streaming + invoke + history management
  /tasks   – Celery task status polling

Health:
  GET /health  – liveness probe (DB ping + Chroma ping)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langchain_ollama import ChatOllama, OllamaEmbeddings

from docseer.agents.basic_agent import BasicAgent
from docseer.databases.chroma import ChromaVectorDB
from docseer.databases.localfilestore import LocalFileStoreDB
from docseer.retrievers.retriever import Retriever

from .config import get_settings
from .database import async_engine
from .models.paper import Base
from .ollama_utils import ensure_models
from .routers import chat_router, papers_router, settings_router, tasks_router

logger = logging.getLogger(__name__)


async def _warmup_model(llm: ChatOllama, model_name: str) -> None:
    """
    Fire a minimal request so Ollama loads model weights into Metal/GPU memory
    before the first real user query.  Runs as a background task — startup is
    not blocked.
    """
    try:
        logger.info("Warming up LLM model '%s' in background…", model_name)
        await llm.ainvoke("hi")
        logger.info("LLM warm-up complete.")
    except Exception as exc:
        logger.warning("LLM warm-up failed (non-fatal): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified / created.")

    if settings.ollama_pull_on_startup:
        models_to_pull = list(
            dict.fromkeys([settings.llm_model, settings.embedding_model])
        )
        logger.info("Ensuring Ollama models are present: %s", models_to_pull)
        await ensure_models(models_to_pull, settings.ollama_base_url)
    else:
        logger.info("ollama_pull_on_startup=False — skipping model pull.")

    embeddings = OllamaEmbeddings(
        model=settings.embedding_model,
        base_url=settings.ollama_base_url,
    )

    vector_db = ChromaVectorDB(
        model_embeddings=embeddings,
        batch_size=settings.embedding_batch_size,
        chroma_host=settings.chroma_host,
        chroma_port=settings.chroma_port,
    )
    docstore = LocalFileStoreDB(path_db=settings.docstore_path)

    retriever = Retriever(
        vector_db=vector_db,
        docstore=docstore,
        topk=settings.retriever_topk,
    )

    llm = ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        keep_alive=settings.chat_model_keep_alive,
        temperature=settings.chat_temperature,
        num_ctx=settings.chat_num_ctx,
        num_predict=settings.chat_num_predict,
    )
    agent = BasicAgent(llm_model=llm, max_turns=settings.chat_history_turns)

    app.state.retriever = retriever
    app.state.agent = agent

    asyncio.create_task(
        _warmup_model(llm.bind(reasoning=False), settings.llm_model)
    )

    logger.info(
        "Agent ready — LLM: %s  embeddings: %s  topk: %d",
        settings.llm_model,
        settings.embedding_model,
        settings.retriever_topk,
    )

    yield

    await async_engine.dispose()
    logger.info("Async engine disposed.")


app = FastAPI(
    title="DocSeer API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(papers_router)
app.include_router(chat_router)
app.include_router(tasks_router)
app.include_router(settings_router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    """
    Liveness probe.

    Pings the async DB connection and the ChromaDB HTTP client.
    Returns {"status": "ok"} on success; raises 503 on failure (FastAPI will
    return a 500 but the intent is the same for a probe).
    """
    from sqlalchemy import text

    from .database import AsyncSessionFactory

    results: dict = {}

    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        results["postgres"] = "ok"
    except Exception as exc:
        results["postgres"] = f"error: {exc}"

    try:
        retriever: Retriever = app.state.retriever
        import asyncio

        await asyncio.to_thread(retriever.vector_db.client.heartbeat)
        results["chromadb"] = "ok"
    except Exception as exc:
        results["chromadb"] = f"error: {exc}"

    results["status"] = (
        "ok" if all(v == "ok" for v in results.values()) else "degraded"
    )
    return results
