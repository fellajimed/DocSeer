import torch
import numpy as np
from transformers import AutoTokenizer, AutoModelForCausalLM


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
