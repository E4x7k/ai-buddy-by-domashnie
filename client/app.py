import streamlit as st
import requests 
import uuid
import json

if "messages" not in st.session_state: #пустая история с сообщениями от пользователя
    st.session_state.messages = []

if "session_id" not in st.session_state: #дает сессии id    
    st.session_state.session_id = str(uuid.uuid4()) #Создание id сессии


checklist = ["Опция 1", "Опция 2", "Опция 3", "Опция 4"] 
try:
   response = requests.get("http://127.0.0.1:8000/checklist") 
except:
    st.error("Бэкенд недоступен")
#пока бэкэнда нет

# ----САЙДБАР----

with st.sidebar:
    choise = st.radio("Я:", ["intern", "mentor"])
    st.session_state.user_role = choise   #Сохранение роли 

    if st.session_state.user_role == "mentor":
        dis = True
    else:                                       
        dis = False
    for list in checklist:
        check = st.checkbox(list,disabled=dis)
        if check:   
            try: 
                request = requests.post("http://127.0.0.1:8000/checklist",json={"item_id": '<id>'})
                st.rerun()
            except:
                st.error("Бэкенд недоступен") 
            st.write("Тут должен быть запрос")
    
    
    cleaning = st.button("Очистить историю")
    if cleaning:
        st.session_state.session_id = str(uuid.uuid4()) # Кнопка очищающая историю собщений и создающая новый id
        st.session_state.messages = []

st.title(f"Доброго времени суток, {st.session_state.user_role}")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander("📚 Источники"):
                for src in message["sources"]:
                    st.write(f"- {src}")

if prompt := st.chat_input("Задайте вопрос..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        sources_placeholder = st.empty()
        text_placeholder = st.empty()
        
        full_response = ""
        current_sources = []

        try:
            payload = {
                "session_id": st.session_state.session_id,
                "message": prompt,
                "user_role": st.session_state.user_role
            }
            
            with requests.post("http://127.0.0.1:8000/chat", json=payload, stream=True, timeout=60) as response:
                response.raise_for_status()

                for line in response.iter_lines(decode_unicode=True):
                    if not line: continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    if "sources" in data:
                        current_sources = data["sources"]
                        if current_sources:
                            with sources_placeholder.expander("📚 Источники (найдены)"):
                                for src in current_sources:
                                    st.write(f"- {src}")
                    
                    elif "text" in data:
                        full_response += data["text"]
                        text_placeholder.markdown(full_response + "▌")
            
            text_placeholder.markdown(full_response)
            
            st.session_state.messages.append({
                "role": "assistant", 
                "content": full_response,
                "sources": current_sources
            })

        except Exception as e:
            st.error(f"Ошибка соединения: {e}")