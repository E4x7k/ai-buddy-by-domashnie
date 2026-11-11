import json
import logging
import os
import sys
import sqlite3
import random
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import AsyncGenerator

import chromadb
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

from backend.schemas import ChatRequest,ToggleChecklistRequest,ChecklistResponse,VacationRequest,ActionResponse,AccessRequest
from backend.services.checklist_service import init_checklist_db,get_checklist,toggle_item
from backend.services.embedder import get_embedder
from backend.services.memory import init_db, get_history, save_message
from ml_core.rag_engine import RAGService

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Запуск приложения...")
    logger.info("Иницализация чеклиста")
    init_checklist_db()
    init_db()
    
    logger.info("Загрузка модели эмбеддингов...")
    embedder = get_embedder()
    
    logger.info("Подключение к ChromaDB...")
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    collection = chroma_client.get_or_create_collection(name="knowledge_base")
    
    logger.info("Инициализация AsyncOpenAI клиента...")
    llm_client = AsyncOpenAI(
        api_key=os.getenv("API_KEY"), 
        base_url=os.getenv("BASE_URL")
    )
    
    app.state.rag_service = RAGService(embedder, collection, llm_client)
    
    logger.info("Приложение успешно запущено.")
    yield
    logger.info("Выключение сервера...")

app = FastAPI(title='Avito AI-buddy Backend', lifespan=lifespan)
START_TIME = datetime.now(UTC)

@app.get("/checklist",tags=["checklist"],response_model=ChecklistResponse)
def checklist():
    """Эндпоинт для вывода чеклиста"""
    connection=sqlite3.connect("buddy.db")
    result=get_checklist(connection)
    return result
@app.get("/health", tags=["system"])
async def health_check():
    now = datetime.now(UTC)
    return {
        "status": "ok",
        "version": app.version,
        "uptime_seconds": round((now - START_TIME).total_seconds(), 2),
        "timestamp": now.isoformat(),
    }

@app.post("/checklist/toggle",tags=["checklist"])
def toggle_checklist(request: ToggleChecklistRequest):
    """Эндпоинт для изменения значение у таски"""
    ask=toggle_item(request.item_id)
    if ask==False:
        raise HTTPException(status_code=404,detail="Задачи нет")
    return {"status": "success"}


@app.post("/actions/vacation",response_model=ActionResponse,tags=["requests"])
def request_time_off(request: VacationRequest):
    """Эндпоинт, создающий заявку на отгул"""
    ticket_id=random.randint(1000,9999)
    message=f"Заявка на отгул на {request.date} по причине '{request.reason}' создана."
    return {"status": "success",
            "ticket_id": ticket_id,
            "message": message}
    

@app.post("/actions/access",response_model=ActionResponse,tags=["requests"])
def request_corp_service(request: AccessRequest):
    """Эндпоинт, создающий заявку на доступ к сервису"""
    ticket_id=random.randint(1000,9999)
    message=f"Заявка на доступ к {request.resource} отправлена в Service Desk."
    return {"status": "success",
            "ticket_id": ticket_id,
            "message": message}
    
    
@app.post("/chat", tags=["chat"])
async def chat_endpoint(req: ChatRequest, request: Request):
    """Эндпоинт для общения с AI-buddy (с поддержкой стриминга)."""
    rag_service: RAGService = request.app.state.rag_service
    
    history = get_history(req.session_id, limit=6)
    
    save_message(req.session_id, "user", req.message)

    # Обертка для стриминга. Нам нужно перехватывать куски текста,
    # чтобы в конце склеить их и сохранить в БД.
    async def stream_wrapper() -> AsyncGenerator[str, None]:
        full_response = ""
        sources = []
        
        async for chunk_str in rag_service.stream_ask(req.message, history, req.user_role):
            try:
                data = json.loads(chunk_str)
                if "text" in data:
                    full_response += data["text"]
                elif "sources" in data:
                    sources = data["sources"]
            except json.JSONDecodeError:
                pass
            
            yield chunk_str
            
        # Когда стрим закончился, сохраняем полный ответ в БД
        save_message(req.session_id, "assistant", full_response, sources=sources)
        logger.info("Ответ ассистента сохранен в БД для сессии %s", req.session_id)

    # Возвращаем стриминговый ответ
    return StreamingResponse(
        stream_wrapper(), 
        media_type="application/x-ndjson" # Формат JSON Lines
    )