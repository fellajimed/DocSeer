pdf_metadata: docker run -t --rm -p 8070:8070 grobid/grobid:0.8.2-crf
pdf2md:       uvicorn backend.pdf2md.main:app --port 8001
chunking:     uvicorn backend.chunking.main:app --port 8002
retriever:    uvicorn backend.retriever.main:app --port 8003
chatbot:      uvicorn backend.chatbot.main:app --port 8000
