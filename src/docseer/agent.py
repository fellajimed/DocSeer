import torch
import numpy as np
from abc import ABC, abstractmethod
from operator import itemgetter
from tqdm import tqdm
from faiss import IndexFlatIP, normalize_L2
from transformers import pipeline
from transformers import AutoTokenizer, AutoModelForCausalLM
from sentence_transformers import SentenceTransformer
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate


class Agent(ABC):
    @abstractmethod
    def retrieve(self):
        ...


class LocalDocAgent(Agent):
    def __init__(self, text_embedder):
        self.template = (
            "You are an exeprt in answering questions about reseach papers."
            "\n\nHere are some relevant context: {context}"
            "\n\nHere is the question to answer: {question}"
        )
        self.model = OllamaLLM(model="llama3.2")
        self.prompt = ChatPromptTemplate.from_template(self.template)
        self.chain = self.prompt | self.model

        self.text_embedder = text_embedder

    def retrieve(self, query: str) -> str:
        context = self.text_embedder.invoke(query)
        return self.chain.invoke({"context": context, "question": query})


class DocAgent(Agent):
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
        self.indexer = FindClosest(self.embeddings)

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


class FindClosest:
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


class Encoder:
    model_name = "google/gemma-3-270m"

    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(self.model_name)
        self.embedder = self.get_embeddings()

    def get_embeddings(self):
        @torch.no_grad()
        def _embeddings(text):
            tokens = self.tokenizer(text)['input_ids']
            if isinstance(tokens[0], int):
                tokens = [tokens]

            return [
                self.model.model.embed_tokens(
                    torch.tensor(t, dtype=torch.int)
                ).detach().cpu().numpy()
                for t in tokens
            ]
        return _embeddings

    def encode(self, text: str | list[str], **kwargs) -> np.ndarray:
        if isinstance(text, str):
            text = [text]

        # Tokenize with padding and truncation
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            padding=True,
            truncation=True
        )

        outputs = self.model(**inputs, output_hidden_states=True,
                             return_dict=True)
        hidden_states = outputs.hidden_states[-1]

        # Apply mean pooling (ignoring padded tokens)
        attention_mask = inputs["attention_mask"]
        mask = attention_mask.unsqueeze(-1).expand(
            hidden_states.size()).float()
        masked_embeddings = hidden_states * mask

        sum_embeddings = torch.sum(masked_embeddings, dim=1)
        sum_mask = torch.clamp(mask.sum(dim=1), min=1e-9)
        return (sum_embeddings / sum_mask).detach().cpu().numpy()
