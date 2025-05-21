class DocAgent:
    def __init__(self, text: str) -> None:
        self.text = text
        self.summarizer = None
        self.retriever = None

    def summarize(self) -> str:
        if self.summarizer is None:
            ...

        return 'summarize'

    def retrieve(self, query: str) -> str:
        if self.retriever is None:
            ...

        return 'retrieve'
