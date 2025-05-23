# 📄 DocSeer

**DocSeer** is an intelligent PDF analysis tool that allows you to **summarize** documents and **ask questions** about their contents using natural language. It leverages modern language models to provide fast, accurate insights from complex files — no more endless scrolling or manual skimming.

---

## ✨ Features

* 🔍 Summarize entire PDFs
* 💬 Ask questions and get accurate answers based on document content
* 🧠 Powered by state-of-the-art AI models
* 📎 Simple, scriptable API or CLI use

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

```bash
usage: DocSeer [-h] [-u URL] [-f FILE_PATH] [-a ARXIV_ID] [-S] [-I]

options:
  -h, --help            show this help message and exit
  -u URL, --url URL
  -f FILE_PATH, --file-path FILE_PATH
  -a ARXIV_ID, --arxiv-id ARXIV_ID
  -S, --summarize
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
