FROM ollama/ollama:latest

WORKDIR /app

EXPOSE 11434

COPY ./entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

RUN /entrypoint.sh
