# Начало работы

```bash
git clone https://github.com/E4x7k/ai-buddy-by-domashnie.git
uv sync
```

# Запуск

### 0. Подготовка

- Распаковать архив data.rar в папку data в корне проекта
Далее синхронизируем зависимости (каждый раз как меняются), скачиваем эмбеддер (1 раз) и наполняем базу знаний (каждый раз, как data меняется (я буду об этом уведомлять — сейчас база знаний урезана, чтобы её векторизирование не занимало 40 минут))
```bash
uv sync
uv run python setup_embedder.py
uv run python -m ml_core.ingest
```

Также необходимо заполнить .env файл (поля для заполнения в .env.example)

### 1. Сервер (запускать теперь из корня проекта)

```bash
uvicorn backend.main:app --reload
```

### 2. Клиент

```bash
cd client
streamlit run app.py
```
