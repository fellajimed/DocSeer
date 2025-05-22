import os
import torch
import pymupdf
import requests
from tempfile import NamedTemporaryFile
from langchain_text_splitters import RecursiveCharacterTextSplitter


def get_device(device: str | None = None) -> torch.device:
    if device is not None:
        return torch.device(device)
    elif torch.backends.mps.is_available():
        return torch.device('mps')
    elif torch.cuda.is_available():
        return torch.device('cuda')
    else:
        return torch.device('cpu')


class TextExtractor:
    def __init__(self, *, url: str | None = None,
                 fname: str | os.PathLike[str] | None = None,
                 chunk_size=100, chunk_overlap=100) -> None:
        # XOR operator
        if not ((url is not None) ^ (fname is not None)):
            raise ValueError('Either `url` or `fname` should be specified:',
                             f'{url=} - {fname=}')

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            length_function=len, is_separator_regex=False,
        )

        self._text = self.process(url=url, fname=fname)

    @property
    def text(self) -> str:
        return self._text

    @property
    def chunks(self) -> list[str]:
        return self.text_splitter.split_text(self._text)

    def process(self, *, url: str | None = None,
                fname: str | os.PathLike[str] | None = None) -> str:
        # save the pdf in the url to a temporary file
        if url is not None:
            response = requests.get(url)
            response.raise_for_status()

            tmp_file = NamedTemporaryFile(delete=False)
            tmp_file.write(response.content)
            tmp_file.flush()
            fname = tmp_file.name

        assert fname is not None
        text = self.extract_text(fname)

        # delete the temporary file
        if url is not None:
            os.remove(fname)

        return text

    def extract_text(self, fname: str | os.PathLike[str] | None) -> str:
        text = ""

        try:
            with pymupdf.open(fname) as doc:  # type: ignore[no-untyped-call]
                for page in doc:
                    text += page.get_text()
        except Exception as e:
            print(e)

        return text


if __name__ == "__main__":
    txt_extractor = TextExtractor(url='https://arxiv.org/pdf/2407.12211')
