import faiss
import torch
import numpy as np
from operator import itemgetter
from functools import partial
from tqdm import tqdm
from transformers import pipeline
from sentence_transformers import SentenceTransformer


class FindClosest:
    def __init__(self, embeddings: np.ndarray) -> None:
        # normalize the weight vector for cosine similarity
        faiss.normalize_L2(embeddings)

        self.index = faiss.IndexFlatIP(embeddings.shape[-1])
        self.index.add(embeddings)

    def __call__(self, input_embedding: np.ndarray, top_k: int = 3,
                 ) -> list[int]:
        faiss.normalize_L2(input_embedding)
        return self.index.search(input_embedding, top_k)[1][0]


class DocAgent:
    sum_model = "Falconsai/text_summarization"
    enc_model = "sentence-transformers/all-MiniLM-L6-v2"
    qa_model = "distilbert/distilbert-base-cased-distilled-squad"

    def __init__(self, text: str, chunks: list[str],
                 device: torch.device = torch.device('cpu')) -> None:
        self.text = text
        self.chunks = chunks
        self.device = device

        self.encoder = partial(SentenceTransformer(self.enc_model).encode,
                               convert_to_numpy=True)
        self.question_answerer = pipeline("question-answering",
                                          model=self.qa_model,
                                          device=device)
        self.embeddings = self.encoder(self.chunks)
        self.indexer = FindClosest(self.embeddings)

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
        query_embedding = self.encoder(query).reshape(1, -1)
        indices = self.indexer(query_embedding)
        closest_chunks = itemgetter(*indices)(self.chunks)

        print(closest_chunks)

        return self.question_answerer(
            question=query, context="\n".join(closest_chunks)
        )['answer']
