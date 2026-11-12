from pydantic import BaseModel, Field

# для RAG

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Уникальный ID сессии для сохранения истории")
    message: str = Field(..., description="Текст вопроса от пользователя")
    user_role: str = Field(default="intern", description="Роль пользователя: 'intern' или 'mentor'")

class ChatResponse(BaseModel):
    # Этот класс мы используем только для Swagger-документации.
    # В реальности эндпоинт /chat будет возвращать StreamingResponse.
    answer: str = Field(..., description="Финальный ответ от LLM")
    sources: list[str] = Field(default_factory=list, description="Список документов, откуда взята информация")


# Для чек-листа

class ChecklistItem(BaseModel):
    id: int = Field(..., description="Уникальный ID задачи")
    title: str = Field(..., description="Название задачи")
    is_completed: bool = Field(default=False, description="Статус выполнения")

class ChecklistResponse(BaseModel):
    items: list[ChecklistItem] = Field(..., description="Список всех задач чек-листа")
    progress_percentage: float = Field(..., description="Процент выполненных задач")

class ToggleChecklistRequest(BaseModel):
    item_id: int = Field(..., description="ID задачи, которую нужно отметить")


# Для взаимодействия с корпоративными сервисами

class VacationRequest(BaseModel):
    date: str = Field(..., description="Дата отгула (в формате YYYY-MM-DD)")
    reason: str = Field(..., description="Причина отгула")

class ActionResponse(BaseModel):
    # Универсальный ответ для всех имитаций корпоративных сервисов
    status: str = Field(..., description="Статус операции: 'success' или 'error'")
    message: str = Field(..., description="Текст для отображения пользователю")
    ticket_id: int | None = Field(default=None, description="Номер созданной заявки при наличии")
    
class AccessRequest(BaseModel):
    resource: str = Field(...,description="Корпоративный сервис")
