#!/bin/sh
set -e

echo "=== ПРОВЕРКА ОКРУЖЕНИЯ ==="

if [ ! -f "/app/models/labse-ru-turbo-onnx/model.onnx" ]; then
    echo "Модель не найдена. Запускаю скачивание и конвертацию (займет время)..."
    uv run python setup_embedder.py
else
    echo "Модель уже на месте, пропускаю."
fi

if [ ! -d "/app/chroma_db" ] || [ -z "$(ls -A /app/chroma_db)" ]; then
    echo "База знаний пуста. Запускаю ingest.py (нарезка и эмбеддинги)..."
    uv run python ingest.py
else
    echo "База знаний уже на месте, пропускаю."
fi

echo "=== ЗАПУСК СЕРВЕРА ==="
exec "$@"