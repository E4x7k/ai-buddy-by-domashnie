import asyncio
import json
import logging
from typing import AsyncGenerator
import os

from fastembed import TextEmbedding
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self, embedder: TextEmbedding, collection, llm_client: AsyncOpenAI):
        self.embedder = embedder
        self.collection = collection
        self.llm_client = llm_client

    async def _rewrite_query(self, history: list, question: str) -> str:
        """Переформулирует вопрос с учетом контекста диалога."""
        if not history:
            return question

        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])

        prompt = (
            "Ты — эксперт по поиску в корпоративной базе знаний Авито. "
            "Твоя задача — переформулировать новый вопрос стажера, используя контекст диалога, "
            "чтобы поиск по базе (Playbook, инструкции) работал идеально.\n"
            "Правила:\n"
            "1. Замени местоимения (там, в нём, у него) на конкретные термины Авито (например, 'Jira', 'наставник').\n"
            "2. Если вопрос уже понятен, верни его без изменений.\n"
            "3. Выведи ТОЛЬКО текст вопроса. Без кавычек и пояснений.\n\n"
            f"История диалога:\n{history_text}\n\n"
            f"Новый вопрос: {question}\n\n"
            "Переформулированный вопрос:"
        )

        try:
            response = await self.llm_client.chat.completions.create(
                model=os.getenv("MODEL"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1, 
                max_tokens=100
            )
            rewritten = response.choices[0].message.content.strip()
            
            if len(rewritten.split()) < 3:
                logger.warning("LLM выдала бред: '%s'.fallback.", rewritten)
                last_user_msg = next((msg['content'] for msg in reversed(history) if msg['role'] == 'user'), "")
                return f"{last_user_msg} {question}"
                
            logger.info("Исходный: '%s' -> Переформулирован: '%s'", question, rewritten)
            return rewritten
        except Exception as e:
            logger.error("Ошибка при переформулировке: %s", e)
            return question

    async def stream_ask(self, question: str, history: list, user_role: str) -> AsyncGenerator[str, None]:
        """
        Основной метод. Принимает вопрос, историю и роль, возвращает стрим JSONL.
        """
        search_query = await self._rewrite_query(history, question)

        def _embed():
            return list(self.embedder.embed([search_query]))[0].tolist()
        query_vector = await asyncio.to_thread(_embed)

        results = self.collection.query(query_embeddings=[query_vector], n_results=4)
        
        if not results['documents'] or not results['documents'][0]:
            context = "База знаний пуста."
            sources = []
        else:
            context = "\n\n".join(results['documents'][0])
            metadatas = results['metadatas'][0]
            sources = list(set([meta.get('source', 'Неизвестно') for meta in metadatas]))
            
        yield json.dumps({"sources": sources}, ensure_ascii=False) + "\n"

        if user_role == "mentor":
            role_rule = (
                "Ты общаешься с наставником. Ты можешь просматривать прогресс стажера и давать советы, "
                "но ты КАТЕГОРИЧЕСКИ НЕ ДОЛЖЕН выполнять действия (оформлять отгулы, запрашивать доступы) от имени стажера. "
                "Если наставник просит оформить отгул, вежливо откажи."
            )
        else:
            role_rule = (
                "Ты общаешься со стажером. Ты должен помогать ему с онбордингом и инструментами (Jira, Git). "
                "Если стажер просит оформить отгул, ты должен использовать доступный тебе инструмент (Tool) для этого."
            )

        system_prompt = (
            "Ты — AI-buddy, дружелюбный ИИ-помощник для адаптации стажеров в компании Авито. "
            "Твоя задача — отвечать на вопросы, используя ТОЛЬКО предоставленный контекст.\n"
            "Правила:\n"
            "1. Внимательно читай контекст.\n"
            "2. Если в контексте нет прямого ответа, честно скажи: 'Я не нашел этой информации в базе знаний.'\n"
            "3. Не выдумывай факты.\n"
            f"4. {role_rule}"
        )

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
            
        messages.append({
            "role": "user", 
            "content": f"Контекст из базы знаний:\n{context}\n\nВопрос пользователя: {question}"
        })

        # Описание инструментов
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "request_vacation",
                    "description": "Оформляет заявку на отгул для стажера",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string", "description": "Дата отгула (в формате YYYY-MM-DD)"},
                            "reason": {"type": "string", "description": "Причина отгула"}
                        },
                        "required": ["date", "reason"]
                    }
                }
            }
        ]

        logger.info("Отправка запроса в LLM...")
        
        available_tools = tools if user_role == "intern" else None

        response = await self.llm_client.chat.completions.create(
            model=os.getenv("MODEL"),
            messages=messages,
            temperature=0.1,
            stream=True,
            tools=available_tools,
            tool_choice="auto" if available_tools else "none"
        )

        tool_calls_to_process = []
        
        try:
            async for chunk in response:
                if not chunk.choices:
                    continue
                
                delta = chunk.choices[0].delta
                
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index == len(tool_calls_to_process):
                            tool_calls_to_process.append({"id": tc.id, "name": tc.function.name, "arguments": ""})
                        if tc.function.arguments:
                            tool_calls_to_process[tc.index]["arguments"] += tc.function.arguments
                
                if delta.content:
                    yield json.dumps({"text": delta.content}, ensure_ascii=False) + "\n"

        except Exception as e:
            logger.warning("Ошибка стриминга: %s", e)
            return

        # Обработка вызова инструмента
        if tool_calls_to_process:
            logger.info("LLM запросила вызов инструментов: %s", tool_calls_to_process)
            
            messages.append({
                "role": "assistant",
                "tool_calls": [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}} for tc in tool_calls_to_process]
            })

            for tc in tool_calls_to_process:
                if tc["name"] == "request_vacation":
                    # заменить на вызов функции
                    args = json.loads(tc["arguments"])
                    logger.info("Симуляция оформления отгула: %s", args)
                    
                    mock_result = {
                        "status": "success", 
                        "message": f"Заявка на отгул на {args.get('date')} успешно создана.", 
                        "ticket_id": 420
                    }
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(mock_result, ensure_ascii=False)
                    })

            logger.info("Отправка результата инструмента обратно в LLM...")
            final_response = await self.llm_client.chat.completions.create(
                model="deepseek-v4.1-flash",
                messages=messages,
                temperature=0.1,
                stream=True
            )
            
            try:
                async for chunk in final_response:
                    if not chunk.choices: continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield json.dumps({"text": delta.content}, ensure_ascii=False) + "\n"
            except Exception as e:
                logger.warning("Ошибка финального стриминга: %s", e)