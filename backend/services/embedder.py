import logging
import os
from pathlib import Path

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

logger = logging.getLogger(__name__)

# Корень репозитория: backend/services/embedder.py -> <корень проекта>
PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_NAME = "labse-ru-turbo-onnx"
# Локальный каталог с моделью. Путь можно переопределить переменной окружения EMBEDDING_MODEL_PATH.
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / MODEL_NAME


def get_embedder() -> TextEmbedding:
    """Загружает и возвращает модель эмбеддингов labse-ru-turbo-onnx.

    Модель берётся из локального каталога ``models/labse-ru-turbo-onnx`` в корне проекта.
    Путь вычисляется относительно файла модуля (через ``pathlib``), поэтому функция
    одинаково работает при любом рабочем каталоге и на любой операционной системе
    (Windows, macOS, Linux).

    Путь к модели можно переопределить переменной окружения ``EMBEDDING_MODEL_PATH``.

    Returns:
        TextEmbedding: проинициализированная модель эмбеддингов.

    Raises:
        FileNotFoundError: если каталог с файлами модели не найден.
    """
    model_path = Path(os.getenv("EMBEDDING_MODEL_PATH", default=str(DEFAULT_MODEL_PATH)))

    if not model_path.is_dir():
        raise FileNotFoundError(
            f"Каталог модели не найден: {model_path}. "
            f"Поместите модель {MODEL_NAME} в {DEFAULT_MODEL_PATH} "
            "или задайте путь через переменную окружения EMBEDDING_MODEL_PATH."
        )

    logger.info("Загрузка модели эмбеддингов %s из %s", MODEL_NAME, model_path)

    TextEmbedding.add_custom_model(
        model=MODEL_NAME,
        pooling=PoolingType.CLS,
        normalization=True,
        sources=ModelSource(hf=MODEL_NAME),
        dim=768,
        model_file="model.onnx",
    )

    embedder = TextEmbedding(
        model_name=MODEL_NAME,
        specific_model_path=str(model_path),
    )

    logger.info("Модель эмбеддингов %s успешно загружена.", MODEL_NAME)
    return embedder
