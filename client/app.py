import streamlit as st
import requests 
import uuid

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
    
    
    cleaning = st.button("Очиститить историю")
    if cleaning:
        st.session_state.session_id = str(uuid.uuid4()) # Кнопка очищающая историю собщений и создающая новый id
        st.session_state.messages = []

st.title(f'Доброго времени суток , {st.session_state.user_role}')

# ----ЧАТ----

prompt = st.chat_input("Задайте вопрос...")
if prompt:
     st.session_state.messages.append(prompt)
     with st.spinner("Печатает..."):
        try:
            response = requests.post("http://127.0.0.1:8000/chat",json={"session_id": st.session_state.session_id, "message": prompt, "user_role": st.session_state.user_role})
            st.write(response.json()['answer'])
        except:
            st.error("Бэкенд недоступен") 
        st.write('')#Чтобы не ломалось
    # data = response.json()
    # if 'sources' in data:
        # with st.expander("Источники"): 
                # st.write(response.json()["sources"])
for hist in st.session_state.messages:
    st.write(hist)    
    #st.write(response.json()["answer"])

