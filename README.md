# 📄 DocSeer

[![PyPI version](https://badge.fury.io/py/docseer.svg)](https://badge.fury.io/py/docseer)

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
- [`gemma3:4b`](https://ollama.com/library/gemma3:4b) — for natural language understanding and generation (QA & summarization)

To get started, run:

```bash
ollama pull mxbai-embed-large
ollama pull gemma3:4b
```

> NB: These models can be modifed in `src/docseer/__init__.py`

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

2. Install dependencies using [uv](https://docs.astral.sh/uv/):

   ```bash
   uv sync
   ```

This method is ideal for contributing to the project or running `docseer` from source.

---

> 💡 **Note:** Make sure you have [uv](https://docs.astral.sh/uv/getting-started/installation/) installed. You can install it with:
>
> ```bash
> pip install uv
> ```
---

## 🛠 CLI tool

```bash
docseer --help
```

```
usage: DocSeer [-h] [-s [SOURCE ...]] [--n-workers N_WORKERS] [--keep-db] [--sync] [--index] [--show-logs] [--version]

options:
  -h, --help            show this help message and exit
  -s [SOURCE ...], --source [SOURCE ...]
  --n-workers N_WORKERS
  --keep-db
  --sync
  --index
  --show-logs
  --versio
```

### 📥 Supported Input Formats
DocSeer accepts any of the following in the `-s` flag:

* Local PDF file path
* Direct URL to a PDF file (`-u`, `--url`)

---

## 📚 Example Use Cases

* Academic paper summarization

---

## Run the application as a backend


All the services are in the `Procfile` file.

```bash
honcho start
```

---

# 🐳 Running the Project with Docker

Building and starting the services:
```bash
docker compose up --build
```

Running a one-time interactive command in a service container: 
```bash
docker compose run --rm -ti rag-chatbot -s https://arxiv.org/pdf/2407.12211 --top-k 5 -I
```

> NOTE: as for now, it uses models that are stored locally

---

## 🧾 License

MIT License
