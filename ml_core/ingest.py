import logging
import os
import sys
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tqdm import tqdm

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
    """Наполняет векторную базу знаний ChromaDB эмбеддингами текстов из каталога data/."""
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

    for file_path in tqdm(txt_files, desc="Чтение и нарезка файлов"):
        text = file_path.read_text(encoding="utf-8")
        chunks = text_splitter.split_text(text)

        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            all_metadatas.append({"source": file_path.name, "chunk_index": i})
            all_ids.append(f"{file_path.stem}_{i}")

    if not all_chunks:
        logger.warning("Не найдено ни одного текста для загрузки.")
        return

    embedder = get_embedder()
    logger.info("Начинаем векторизацию и сохранение в ChromaDB...")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        client.delete_collection(name=COLLECTION_NAME)
        logger.info("Старая коллекция удалена.")
    except Exception:
        logger.debug("Коллекции %s ещё не существует.", COLLECTION_NAME)

    collection = client.create_collection(name=COLLECTION_NAME)

    batch_size = 64
    for i in tqdm(range(0, len(all_chunks), batch_size), desc="Векторизация и загрузка"):
        batch_chunks = all_chunks[i : i + batch_size]
        batch_metadatas = all_metadatas[i : i + batch_size]
        batch_ids = all_ids[i : i + batch_size]

        batch_embeddings = list(embedder.embed(batch_chunks))

        collection.add(
            documents=batch_chunks,
            embeddings=[emb.tolist() for emb in batch_embeddings],
            metadatas=batch_metadatas,
            ids=batch_ids,
        )

    logger.info("Успешно добавлено %d чанков в базу.", len(all_chunks))


if __name__ == "__main__":
    run_ingest()