import os
import uuid
import json

from .. import CACHE_FOLDER
from .utils import get_sitemap_urls


class Documents:
    # NOTE: when using local file, their processing could be longer
    #       if they are highlighted and have notes
    def __init__(
        self,
        paths: list[str | os.PathLike[str]] | None = None,
        ignore_cache: bool = False,
    ) -> None:
        self.cache_path = CACHE_FOLDER / "docs.json"
        if ignore_cache or not self.cache_path.exists():
            # in case the file does not exist, an empty json file is created
            self.cache_path.write_text("{}", encoding="utf-8")

        self.history_path2ids = json.loads(
            self.cache_path.read_text(encoding="utf-8")
        )

        self.paths2ids = dict()
        if paths is not None:
            for p in paths:
                self.add_source(str(p))

    def add_source(self, source: str) -> None:
        # TODO: replace prints with logger
        if source.endswith("/sitemap.xml"):
            try:
                urls = get_sitemap_urls(source)
                for url in urls:
                    if url in self.paths2ids:
                        print(f"{url} already exists, and it will be ignored")
                    else:
                        self.paths2ids[url] = uuid.uuid4().hex
            except Exception:
                print("Could not extract urls from:", source)
        else:
            if source in self.paths2ids:
                print(f"{source} already exists, and it will be ignored")
            else:
                self.paths2ids[source] = uuid.uuid4().hex

    def pop_source(self, source: str) -> None:
        self.paths2ids.pop(source, None)

    @property
    def cache(self):
        return self.history_path2ids

    @property
    def docs_to_process(self):
        return (
            (k, v)
            for k, v in self.paths2ids.items()
            if k not in self.history_path2ids
        )

    def cache_source(self, path: str | os.PathLike[str]) -> None:
        if path in self.paths2ids:
            self.history_path2ids[path] = self.paths2ids.pop(path)

            self.cache_path.write_text(
                json.dumps(self.history_path2ids, indent=2),
                encoding="utf-8",
            )

    def uncache_source(self, path: str | os.PathLike[str]) -> None:
        if path in self.history_path2ids:
            self.history_path2ids.pop(path)

            self.cache_path.write_text(
                json.dumps(self.history_path2ids, indent=2),
                encoding="utf-8",
            )


if __name__ == "__main__":
    values = [
        "https://arxiv.org/pdf/2407.01985",
        "https://arxiv.org/pdf/2407.12211",
        "https://arxiv.org/pdf/2407.12211",
    ]

    docs = Documents(values)

    docs.add_source(values[0])
    docs.add_source("https://arxiv.org/pdf/2407.12215")
