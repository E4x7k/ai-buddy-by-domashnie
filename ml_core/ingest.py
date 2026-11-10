import logging
import os
import sys
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.services.embedder import get_embedder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = Path(os.getenv("DATA_DIR", default=str(PROJECT_ROOT / "data")))
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", default=str(PROJECT_ROOT / "chroma_db")))
COLLECTION_NAME = "knowledge_base"


def run_ingest() -> None:
    """Наполняет векторную базу знаний ChromaDB эмбеддингами текстов из каталога data/.

    Все файлы ``*.txt`` из каталога ``data/`` нарезаются на чанки, векторизуются моделью
    эмбеддингов и сохраняются в постоянную коллекцию ChromaDB. Существующая коллекция
    удаляется перед записью, чтобы при повторных запусках не появлялись дубликаты.
    """
    if not DATA_DIR.is_dir():
        logger.error("Папка %s не найдена. Создайте её и положите туда .txt файлы.", DATA_DIR)
        return

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        length_function=len,
        separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
    )

    all_chunks = []
    all_metadatas = []
    all_ids = []

    txt_files = list(DATA_DIR.glob("*.txt"))
    logger.info("Найдено %d файлов для обработки.", len(txt_files))

    for file_path in txt_files:
        logger.info("Обработка файла: %s", file_path.name)
        text = file_path.read_text(encoding="utf-8")

        chunks = text_splitter.split_text(text)
        logger.info("  -> Получено %d чанков.", len(chunks))

        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            # Метаданные: из какого файла взят кусок.
            all_metadatas.append({"source": file_path.name, "chunk_index": i})
            # Уникальный ID чанка для ChromaDB.
            all_ids.append(f"{file_path.stem}_{i}")

    if not all_chunks:
        logger.warning("Не найдено ни одного текста для загрузки.")
        return

    embedder = get_embedder()
    logger.info("Вычисление эмбеддингов для %d чанков (это может занять время)...", len(all_chunks))
    embeddings = list(embedder.embed(all_chunks))

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        client.delete_collection(name=COLLECTION_NAME)
        logger.info("Старая коллекция удалена.")
    except Exception:
        logger.debug("Коллекции %s ещё не существует.", COLLECTION_NAME)

    collection = client.create_collection(name=COLLECTION_NAME)
    logger.info("Сохранение в ChromaDB...")

    collection.add(
        documents=all_chunks,
        embeddings=[emb.tolist() for emb in embeddings],
        metadatas=all_metadatas,
        ids=all_ids,
    )
    logger.info("Успешно добавлено %d чанков в базу.", len(all_chunks))


if __name__ == "__main__":
    run_ingest()
