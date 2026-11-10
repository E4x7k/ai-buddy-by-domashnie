import sqlite3
import logging
import json
from typing import List, Dict

logger = logging.getLogger(__name__)
DB_PATH = "chat_history.db"

def init_db():
    """Создает таблицы при старте сервера."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    logger.info("База данных истории чатов инициализирована.")

def save_message(session_id: str, role: str, content: str, sources: List[str] = None):
    """Сохраняет сообщение, опционально прикрепляя список источников."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        sources_json = json.dumps(sources, ensure_ascii=False) if sources else None
        
        cursor.execute(
            "INSERT INTO messages (session_id, role, content, sources) VALUES (?, ?, ?, ?)",
            (session_id, role, content, sources_json)
        )
        conn.commit()

def get_history(session_id: str, limit: int = 50) -> List[Dict]:
    """Достает историю сообщений, распаковывая источники из JSON."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, content, sources FROM messages 
            WHERE session_id = ? 
            ORDER BY timestamp ASC
        """, (session_id,))
        
        rows = cursor.fetchall()
        history = []
        for row in rows:
            msg = {"role": row[0], "content": row[1]}
            if row[2]:
                msg["sources"] = json.loads(row[2])
            else:
                msg["sources"] = []
            history.append(msg)
            
        return history

def delete_session(session_id: str):
    """Удаляет всю историю сообщений для указанной сессии."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.commit()
    logger.info("Сессия %s удалена из базы.", session_id)