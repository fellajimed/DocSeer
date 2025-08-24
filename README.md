# 📄 DocSeer

**DocSeer** is an intelligent PDF analysis tool that allows you to **summarize** documents and **ask questions** about their contents using natural language. It leverages modern language models to provide fast, accurate insights from complex files — no more endless scrolling or manual skimming.

> **Seer**: One who perceives hidden knowledge—interpreting and revealing insights beyond the surface.
---

## ✨ Features

* 🔍 Summarize entire PDFs
* 💬 Ask questions and get accurate answers based on document content
* 🧠 Powered by state-of-the-art AI models
* 📎 Simple, scriptable API or CLI use

---

## ⚙️ Default Behavior

By default, **DocSeer** relies on [**Ollama**](https://ollama.com/) and **local language models** for processing.  
Make sure **Ollama** is installed and any required models are available locally to ensure full functionality.


### 🧠 Models Used

DocSeer uses the following models via Ollama:

- [`mxbai-embed-large`](https://ollama.com/library/mxbai-embed-large) — for high-quality embedding and semantic search  
- [`llama3`](https://ollama.com/library/llama3) — for natural language understanding and generation (QA & summarization)

To get started, run:

```bash
ollama pull mxbai-embed-large
ollama pull llama3
```

---

## 🚀 Installation
Within the project directory, `docseer` and its dependencies could be easily installed:
```bash
pdm install
```

Activate the environment:
```bash
eval $(pdm venv activate)
```
---

## 🛠 CLI tool

```bash
docseer --help
```

```
usage: DocSeer [-h] [-u [URL ...]] [-f [FILE_PATH ...]] [-a [ARXIV_ID ...]] [-k TOP_K] [-Q QUERY] [-I]

options:
  -h, --help            show this help message and exit
  -u [URL ...], --url [URL ...]
  -f [FILE_PATH ...], --file-path [FILE_PATH ...]
  -a [ARXIV_ID ...], --arxiv-id [ARXIV_ID ...]
  -k TOP_K, --top-k TOP_K
  -Q QUERY, --query QUERY
  -I, --interactive
```

### 📥 Supported Input Formats
DocSeer accepts any of the following:

* Local PDF file path (`-f`, `--file-path`)
* Direct URL to a PDF file (`-u`, `--url`)
* arXiv ID (`-a`, `--arxiv-id`)

For URLs and arXiv IDs, the PDF is downloaded to a temporary file, analyzed, and then automatically deleted after use.

---

## 📚 Example Use Cases

* Academic paper summarization

---

## 🧾 License

MIT License
