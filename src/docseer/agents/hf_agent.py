import torch
import numpy as np
from operator import itemgetter
from tqdm import tqdm
from faiss import IndexFlatIP, normalize_L2
from transformers import pipeline
from sentence_transformers import SentenceTransformer

from .base_agent import Agent


class HFDocAgent(Agent):
    sum_model = "Falconsai/text_summarization"
    enc_model = "sentence-transformers/all-MiniLM-L6-v2"
    qa_model = "distilbert/distilbert-base-cased-distilled-squad"

    def __init__(self, text: str, chunks: list[str],
                 device: torch.device = torch.device('cpu')) -> None:
        self.text = text
        self.chunks = chunks
        self.device = device

        self.encoder = SentenceTransformer(self.enc_model)
        self.question_answerer = pipeline("question-answering",
                                          model=self.qa_model,
                                          device=device)
        self.embeddings = self._encode(self.chunks)
        self.indexer = FAISSFindClosest(self.embeddings)

    @torch.no_grad()
    def _encode(self, text: str | list[str]) -> np.ndarray:
        return self.encoder.encode(text, convert_to_numpy=True)

    @torch.no_grad()
    def _summarizer(self, text: str) -> str:
        summarizer = pipeline("summarization", model=self.sum_model,
                              device=self.device)
        return summarizer(text, min_length=10, max_length=40,
                          max_new_tokens=None, do_sample=True,
                          truncation=True)[0]['summary_text']

    @torch.no_grad()
    def summarize(self) -> str:
        return " ".join(list(tqdm(map(self._summarizer, self.chunks),
                                  total=len(self.chunks))))

    @torch.no_grad()
    def retrieve(self, query: str) -> str:
        query_embedding = self._encode(query).reshape(1, -1)
        indices = self.indexer(query_embedding)
        closest_chunks = itemgetter(*indices)(self.chunks)

        return self.question_answerer(
            question=query, context="\n".join(closest_chunks)
        )['answer']


class FAISSFindClosest:
    def __init__(self, embeddings: np.ndarray) -> None:
        if embeddings.ndim != 2:
            raise ValueError("Embeddings must be a 2D array"
                             " (num_vectors, vector_dim)")

        # Copy to avoid mutating original embeddings
        self.embeddings = embeddings.astype(np.float32, copy=True)
        normalize_L2(self.embeddings)

        self.index = IndexFlatIP(self.embeddings.shape[-1])
        self.index.add(self.embeddings)

    def __call__(
        self,
        input_embedding: np.ndarray | list[float],
        top_k: int = 3,
        return_scores: bool = False
    ) -> list[int] | tuple[list[int], list[float]]:
        vec = np.asarray(input_embedding, dtype=np.float32)

        if vec.ndim == 1:
            vec = vec.reshape(1, -1)
        elif vec.ndim != 2 or vec.shape[0] != 1:
            raise ValueError("Input embedding must be a 1D vector"
                             " or a 2D array with shape (1, dim)")

        normalize_L2(vec)

        scores, indices = self.index.search(vec, top_k)

        if return_scores:
            return indices[0].tolist(), scores[0].tolist()
        return indices[0].tolist()
