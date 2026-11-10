from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Отключаем бэкенд загрузки Xet.
os.environ["HF_HUB_DISABLE_XET"] = "1"

# Направляем загрузку через публичное зеркало.
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer


MODEL_ID: str = "sergeyzh/LaBSE-ru-turbo"

SCRIPT_DIR: Path = Path(__file__).resolve().parent

#: Каталог, в котором хранятся подготовленные артефакты модели.
OUTPUT_DIR: Path = SCRIPT_DIR / "models" / "labse-ru-turbo-onnx"

ONNX_PATH: Path = OUTPUT_DIR / "model.onnx"
TOKENIZER_PATH: Path = OUTPUT_DIR / "tokenizer.json"

SAMPLE_TEXT: list[str] = ["Пример текста"]

OPSET_VERSION: int = 14

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# Обёртка модели
class WrappedModel(torch.nn.Module):
    """Отдаёт наружу «сырые» эмбеддинги токенов :class:`SentenceTransformer` как тензор.

    Параметры
    ---------
    st_model : SentenceTransformer
        Нижележащий энкодер sentence-transformer.
    """

    def __init__(self, st_model: SentenceTransformer) -> None:
        super().__init__()
        self.model = st_model

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        token_type_ids: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Вычисляет эмбеддинги на уровне токенов.

        Параметры
        ---------
        input_ids : torch.Tensor
            Идентификаторы токенов, форма ``(batch_size, sequence_length)``.
        attention_mask : torch.Tensor
            Маска внимания, форма ``(batch_size, sequence_length)``.
        token_type_ids : torch.Tensor | None, необязательный
            Данной моделью не используется — оставлен в сигнатуре
            для совместимости по API.

        Возвращает
        ----------
        torch.Tensor
            Эмбеддинги токенов, форма ``(batch_size, sequence_length, hidden_size)``.
        """
        outputs = self.model(
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
        )
        return outputs["token_embeddings"]


def export_onnx() -> None:
    """Скачивает SentenceTransformer-модель и экспортирует её в ONNX.

    Шаг пропускается, если файл :data:`ONNX_PATH` уже существует.
    В случае ошибки процесс завершается со статусом ``1``.
    """
    if ONNX_PATH.exists():
        logger.info("Шаг 1/2: ONNX-модель уже существует, пропускаем экспорт (%s).", ONNX_PATH)
        return

    logger.info("Шаг 1/2: Скачиваем веса и экспортируем в ONNX (это может занять время)...")
    try:
        model = SentenceTransformer(MODEL_ID)
        model.eval()
        wrapped = WrappedModel(model)

        features = model.tokenize(SAMPLE_TEXT)
        input_ids = features["input_ids"]
        attention_mask = features["attention_mask"]

        torch.onnx.export(
            wrapped,
            (input_ids, attention_mask),
            str(ONNX_PATH),
            input_names=["input_ids", "attention_mask"],
            output_names=["token_embeddings"],
            dynamic_axes={
                "input_ids": {0: "batch_size", 1: "sequence_length"},
                "attention_mask": {0: "batch_size", 1: "sequence_length"},
                "token_embeddings": {0: "batch_size", 1: "sequence_length"},
            },
            opset_version=OPSET_VERSION,
        )
        logger.info("ONNX-модель успешно сохранена: %s", ONNX_PATH)
    except Exception:
        logger.exception("Не удалось экспортировать модель в ONNX.")
        sys.exit(1)


def save_tokenizer() -> None:
    """Скачивает и сохраняет токенизатор рядом с ONNX-моделью.

    Шаг пропускается, если файл :data:`TOKENIZER_PATH` уже существует.
    В случае ошибки процесс завершается со статусом ``1``.
    """
    if TOKENIZER_PATH.exists():
        logger.info("Шаг 2/2: Токенизатор уже существует, пропускаем (%s).", TOKENIZER_PATH)
        return

    logger.info("Шаг 2/2: Скачиваем и сохраняем токенизатор...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, use_fast=False)
        tokenizer.save_pretrained(OUTPUT_DIR)
        logger.info("Файлы токенизатора успешно сохранены в: %s", OUTPUT_DIR)
    except Exception:
        logger.exception("Не удалось подготовить токенизатор.")
        sys.exit(1)


# Точка входа
def setup_model() -> None:
    """Гарантирует наличие ONNX-модели и токенизатора локально.

    Создаёт каталог :data:`OUTPUT_DIR` при необходимости, затем выполняет
    оба шага подготовки. Оба шага идемпотентны: существующие артефакты
    переиспользуются как есть.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export_onnx()
    save_tokenizer()
    logger.info("Подготовка модели полностью завершена.")


if __name__ == "__main__":
    setup_model()