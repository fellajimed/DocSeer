from pathlib import Path
from langchain_ollama.llms import OllamaLLM
from langchain_ollama import OllamaEmbeddings
from importlib.metadata import version, PackageNotFoundError


# LLM_MODEL = OllamaLLM(model="llama3.2", temperature=0.2, top_p=0.15)
MODEL_EMBEDDINGS = OllamaEmbeddings(model="mxbai-embed-large")
SMALL_LLM_MODEL = None  # OllamaLLM(model="gemma3:270m")
LLM_MODEL = OllamaLLM(model="gemma3:4b", temperature=0.2, top_p=0.1)
# MODEL_EMBEDDINGS = OllamaEmbeddings(model="embeddinggemma:latest")

CACHE_FOLDER = Path(__file__).resolve().absolute().parents[2] / ".cache"
CACHE_FOLDER.mkdir(parents=True, exist_ok=True)


try:
    __version__ = version("docseer")
except PackageNotFoundError:
    __version__ = "0.0.0"


__all__ = ["CACHE_FOLDER", "MODEL_EMBEDDINGS", "LLM_MODEL", "SMALL_LLM_MODEL"]
