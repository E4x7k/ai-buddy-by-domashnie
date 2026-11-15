import asyncio
import json
import logging
from typing import AsyncGenerator
import os
import httpx
from datetime import date

from fastembed import TextEmbedding
from openai import AsyncOpenAI, APIError, RateLimitError, APIConnectionError
from dotenv import load_dotenv

load_dotenv(override=True)
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
        except (APIError, RateLimitError, APIConnectionError) as e:
            logger.error("Ошибка API при переформулировке: %s. Используем fallback.", e)
            return question
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

        if user_role == "mentor":
            role_rule = (
                "Ты общаешься с наставником. Ты можешь просматривать прогресс стажера и давать советы, "
                "но ты КАТЕГОРИЧЕСКИ НЕ ДОЛЖЕН выполнять действия (оформлять отгулы, запрашивать доступы) от имени стажера. "
                "Если наставник просит оформить отгул, вежливо откажи."
            )
        else:
            role_rule = (
                "Ты общаешься со стажером. Твоя главная задача — использовать инструменты (Tools) для помощи. "
                "Если стажер просит оформить отгул или сообщает о болезни — ОБЯЗАТЕЛЬНО вызывай 'request_vacation'. "
                "Если стажер просит доступ к любому корпоративному инструменту (Jira, Confluence, GitHub и т.д.) — ОБЯЗАТЕЛЬНО вызывай 'request_access'. "
                "Никогда не пиши, что ты 'оформляешь заявку', просто вызови функцию."
            )

        # 1. Оборачиваем контекст в теги (LLM так лучше понимают, где данные)
        context_block = f"<context>\n{context}\n</context>"

        # 2. Обновленный системный промпт
        system_prompt = (
            "Ты — AI-buddy, экспертный ИИ-помощник для адаптации стажеров в Авито. "
            "Твоя задача — давать точные, структурированные и полезные ответы, опираясь на предоставленный контекст.\n\n"
            "Правила работы с информацией:\n"
            "1. Если вопрос просит СРАВНИТЬ два понятия (например, 'чем отличается А от Б'), найди в контексте информацию об обоих понятиях и самостоятельно сформулируй сравнение по пунктам.\n"
            "2. Отвечай структурированно, но КРАТКО. Твоя цель — дать суть. Используй списки, но ограничивайся 3-5 ключевыми пунктами. Избегай вступлений вроде 'Отличный вопрос!' или 'Конечно, я с радостью отвечу'. \n"
            "3. Категорически ЗАПРЕЩЕНО выдумывать факты, которых нет в контексте. Если в контексте нет информации для ответа, вежливо скажи: 'К сожалению, в предоставленной базе знаний нет информации по этому вопросу.'\n"
            f"4. {role_rule}\n"
            "5. Не предлагай пользователю 'разобрать что-то подробнее', если он об этом не просил. Просто дай лучший ответ на текущий вопрос."
        )

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
            
        messages.append({
            "role": "user", 
            "content": f"Вот данные из базы знаний Авито:\n{context_block}\n\nВопрос пользователя: {question}"
        })

        today_str = date.today().isoformat()

        # Описание инструментов
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "request_vacation",
                    "description": f"Оформляет заявку на отгул для стажера. Сегодняшняя дата: {today_str}. Используй, если стажер просит отгул или сообщает, что заболел.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string", "description": "Дата отгула (в формате YYYY-MM-DD)"},
                            "reason": {"type": "string", "description": "Причина отгула (например, 'Болезнь')"}
                        },
                        "required": ["date", "reason"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "request_access",
                    "description": "Создает заявку на доступ к корпоративным инструментам (Jira, Confluence, GitHub, Figma и т.д.).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "resource": {"type": "string", "description": "Название инструмента"}
                        },
                        "required": ["resource"]
                    }
                }
            }
        ]

        logger.info("Отправка запроса в LLM...")
        
        available_tools = tools if user_role == "intern" else None

        try:
            response = await self.llm_client.chat.completions.create(
                model=os.getenv("MODEL"),
                messages=messages,
                temperature=0.1,
                stream=True,
                tools=available_tools,
                tool_choice="auto" if available_tools else "none"
            )
        except (APIError, RateLimitError, APIConnectionError) as e:
            logger.error("Ошибка API при основном запросе: %s", e)
            error_msg = "⚠️ Ошибка: Сервис LLM временно недоступен (проблема с API-ключом или лимитами). Попробуйте позже."
            yield json.dumps({"text": error_msg}, ensure_ascii=False) + "\n"
            return
        except Exception as e:
            logger.error("Неизвестная ошибка LLM: %s", e)
            yield json.dumps({"text": "⚠️ Внутренняя ошибка при обращении к нейросети."}, ensure_ascii=False) + "\n"
            return

        tool_calls_dict = {} # <--- ИСПОЛЬЗУЕМ СЛОВАРЬ ВМЕСТО СПИСКА
        
        try:
            async for chunk in response:
                if not chunk.choices:
                    continue
                
                delta = chunk.choices[0].delta
                
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        # Если такого индекса еще нет, создаем для него запись
                        if tc.index not in tool_calls_dict:
                            tool_calls_dict[tc.index] = {"id": "", "name": "", "arguments": ""}
                        
                        if tc.id:
                            tool_calls_dict[tc.index]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_dict[tc.index]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_dict[tc.index]["arguments"] += tc.function.arguments
                
                if delta.content:
                    yield json.dumps({"text": delta.content}, ensure_ascii=False) + "\n"

        except Exception as e:
            logger.warning("Ошибка стриминга: %s", e)
            return

        tool_calls_to_process = [v for v in tool_calls_dict.values() if v["name"]]

        if not tool_calls_to_process and sources:
            yield json.dumps({"sources": sources}, ensure_ascii=False) + "\n"

        # Обработка вызова инструмента
        if tool_calls_to_process:
            logger.info("LLM запросила вызов инструментов: %s", tool_calls_to_process)
            
            messages.append({
                "role": "assistant",
                "tool_calls": [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}} for tc in tool_calls_to_process]
            })

            async with httpx.AsyncClient() as client:
                for tc in tool_calls_to_process:
                    try:
                        args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                        
                        if tc["name"] == "request_vacation":
                            logger.info("Вызов API отгула: %s", args)
                            res = await client.post("http://127.0.0.1:8000/actions/vacation", json=args)
                            result_data = res.json()
                            
                        elif tc["name"] == "request_access":
                            logger.info("Вызов API доступа: %s", args)
                            res = await client.post("http://127.0.0.1:8000/actions/access", json=args)
                            result_data = res.json()
                        else:
                            result_data = {"status": "error", "message": "Неизвестный инструмент"}
                            
                    except Exception as e:
                        logger.error("Ошибка вызова API бэкенда: %s", e)
                        result_data = {"status": "error", "message": f"Ошибка сервера: {str(e)}"}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result_data, ensure_ascii=False)
                    })

            logger.info("Отправка результата инструмента обратно в LLM...")
            
            try:
                final_response = await self.llm_client.chat.completions.create(
                    model=os.getenv("MODEL"),
                    messages=messages,
                    temperature=0.1,
                    stream=True
                )
            except Exception as e:
                logger.error("Ошибка API при финальном запросе: %s", e)
                yield json.dumps({"text": "\n\n⚠️ Заявка создана, но не удалось сформировать ответ."}, ensure_ascii=False) + "\n"
                return

            try:
                async for chunk in final_response:
                    if not chunk.choices: continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield json.dumps({"text": delta.content}, ensure_ascii=False) + "\n"
            except Exception as e:
                logger.warning("Ошибка финального стриминга: %s", e)