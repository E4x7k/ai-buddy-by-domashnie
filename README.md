# Начало работы

```bash
git clone https://github.com/E4x7k/ai-buddy-by-domashnie.git
uv sync
```

# Запуск

### 1. Сервер (запускать теперь из корня проекта)

```bash
uvicorn backend.main:app --reload
```

### 2. Клиент

```bash
cd client
streamlit run app.py
```
