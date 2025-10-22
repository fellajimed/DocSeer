#!/bin/sh
set -e

ollama serve &

echo "Waiting for Ollama server to be active..."
# while [ "$(ollama list | grep 'NAME')" == "" ]; do
#   sleep 1
# done

# sleep 10

# ollama pull llama3.2
# ollama pull mxbai-embed-large
