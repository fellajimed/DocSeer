pdf2md:       uvicorn backend.pdf2md.main:app --port ${PDF2MD_PORT}
chunking:     uvicorn backend.chunking.main:app --port ${CHUNKING_PORT}
retriever:    uvicorn backend.retriever.main:app --port ${RETRIEVER_PORT}
chatbot:      uvicorn backend.chatbot.main:app --port ${CHATBOT_PORT}
pdf_metadata: docker run -t --rm --name grobid -p ${PDF_METADATA_PORT}:8070 grobid/grobid:0.8.2.1-crf
chroma: docker run -t --rm --name chroma -p ${CHROMA_PORT}:8000 -v "${DOCSEER_CACHE_FOLDER}/embeds_db":/data -e IS_PERSISTENT=TRUE chromadb/chroma
