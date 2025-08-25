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
- [`llama3.2`](https://ollama.com/library/llama3.2) — for natural language understanding and generation (QA & summarization)

To get started, run:

```bash
ollama pull mxbai-embed-large
ollama pull llama3.2
```

---

## 🚀 Installation

### 📦 Install via pip

To install the latest released version of `docseer` from PyPI:

```bash
pip install docseer
````

This method is recommended if you simply want to use `docseer` as a library or CLI tool without modifying the source code.

---

### 🔧 Local Development Installation

To install `docseer` locally for development:

1. Clone the repository:

   ```bash
   git clone https://github.com/fellajimed/docseer.git
   cd docseer
   ```

2. Install dependencies using [PDM](https://pdm-project.org/en/latest/):

   ```bash
   pdm install
   ```

3. Activate the virtual environment:

   ```bash
   eval "$(pdm venv activate)"
   ```

This method is ideal for contributing to the project or running `docseer` from source.

---

> 💡 **Note:** Make sure you have [PDM](https://pdm-project.org/en/latest/#installation) installed. You can install it with:
>
> ```bash
> pip install pdm
> ```
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
