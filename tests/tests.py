import sqlite3



from backend.main import app
from backend import main
from fastapi.testclient import TestClient
from backend.services import memory
from backend.services.checklist_service import seed_checklist
from unittest.mock import Mock, call

client=TestClient(app)

def test_save_message(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(memory, "DB_PATH", db)

    memory.init_db()
    memory.save_message("123", "user", "Привет")

    with sqlite3.connect(db) as conn:
        result = conn.execute(
            "SELECT session_id, role, content FROM messages"
        ).fetchone()

    assert result == ("123", "user", "Привет")

def test_seed_checklist():
    connection = sqlite3.connect(":memory:")

    seed_checklist(connection)

    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM checklist")

    assert cursor.fetchone()[0] == 6

    connection.close()


def test_access_success():
    response = client.post("/actions/access",json={"resource": "Jira"})
    assert response.status_code == 200
    
    
def test_get_cheklist():
    response=client.get("/checklist")
    assert response.status_code==200
    
    
def test_post_cheklist():
    response=client.post("/checklist/toggle",json={"item_id":"4"})
    assert response.status_code==200
    
    
def test_post_request_time_off():
    response=client.post("/actions/vacation",json={"date":"2026-11-11","reason":"Потому что хочу"})
    assert response.status_code==200


def test_post_request_corp_service():
    response=client.post("/actions/access",json={"resource":"Jira"})
    assert response.status_code==200


def test_init_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(memory, "DB_PATH", db)

    memory.init_db()

    with sqlite3.connect(db) as conn:
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE name='messages'"
        ).fetchone()

    assert result is not None
    
def test_get_history(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(memory, "DB_PATH", db)

    memory.init_db()
    memory.save_message("123", "user", "Привет")
    memory.save_message("123", "assistant", "Привет!", ["Документ"])

    history = memory.get_history("123")

    assert len(history) == 2
    assert history[0]["content"] == "Привет"
    assert history[0]["sources"] == []
    assert history[1]["sources"] == ["Документ"]


def test_delete_session(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(memory, "DB_PATH", db)

    memory.init_db()
    memory.save_message("123", "user", "Привет")

    memory.delete_session("123")

    history = memory.get_history("123")

    assert history == []
    

import pytest
from unittest.mock import MagicMock
from backend.services import embedder


def test_get_embedder_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", str(tmp_path / "missing"))

    with pytest.raises(FileNotFoundError):
        embedder.get_embedder()


def test_get_embedder_success(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL_PATH", str(tmp_path))

    fake_model = MagicMock()
    monkeypatch.setattr(embedder, "TextEmbedding", fake_model)

    result = embedder.get_embedder()

    assert result == fake_model.return_value
    fake_model.add_custom_model.assert_called_once()


def test_chat_endpoint(monkeypatch):
    class FakeRAGService:
        async def stream_ask(self, message, history, user_role):
            yield '{"text": "Привет!"}\n'
            yield '{"sources": ["doc"]}\n'

    monkeypatch.setattr(main.app.state, "rag_service", FakeRAGService(), raising=False)
    monkeypatch.setattr(main, "get_history", lambda session_id, limit: [])

    save_mock = Mock()
    monkeypatch.setattr(main, "save_message", save_mock)

    response = client.post("/chat", json={
        "session_id": "123",
        "message": "Привет",
        "user_role": "intern"
    })

    assert response.status_code == 200
    assert "Привет!" in response.text

    assert save_mock.call_args_list == [
        call("123", "user", "Привет"),
        call("123", "assistant", "Привет!", sources=["doc"])
    ]