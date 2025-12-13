from pathlib import Path
from langchain_ollama.llms import OllamaLLM
from langchain_ollama import OllamaEmbeddings
from importlib.metadata import version, PackageNotFoundError


MODEL_EMBEDDINGS = OllamaEmbeddings(model="mxbai-embed-large")
SMALL_LLM_MODEL = OllamaLLM(model="gemma3:1b")
LLM_MODEL = OllamaLLM(model="gemma3:4b", temperature=0.2, top_p=0.1)

CACHE_FOLDER = Path(__file__).resolve().absolute().parents[2] / ".cache"
CACHE_FOLDER.mkdir(parents=True, exist_ok=True)


try:
    __version__ = version("docseer")
except PackageNotFoundError:
    __version__ = "0.0.0"


__all__ = ["CACHE_FOLDER", "MODEL_EMBEDDINGS", "LLM_MODEL", "SMALL_LLM_MODEL"]
