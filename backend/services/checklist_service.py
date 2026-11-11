import sqlite3
import logging
from pathlib import Path
logger = logging.getLogger(__name__)
def seed_checklist(connection: sqlite3.Connection):
    """Если таблица пуста, добавляет задачи
    
        Args:
            db_path (str): путь к бд
    
        Returns:
            bool: вердикт о существование бд
        """
    cursor=connection.cursor()
    cursor.execute("""
                       CREATE TABLE IF NOT EXISTS checklist(
                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                           title TEXT NOT NULL,
                           is_completed INTEGER DEFAULT 0
                       )
                       """)
    cursor.execute("SELECT COUNT(*) FROM checklist")
    if cursor.fetchone()[0]==0:
        basetasks=[
            ("Познакомится с командой",),
            ("Запроси у куратора стажировки методичку наставника",),
            ("Изучи все необходимые документы и мануалы по работе в своей команде/вертикали/кластеру, которыми с тобой поделился бадди/руководитель",),
            ("Изучи основы защиты персональных данных и другие инструкции Авито",),
            ("Изучи памятку, как закрывать практику, писать учебные работы по Авито",),
            ("Подготовься к экваторной встрече",)
        ]
        cursor.executemany("INSERT INTO checklist (title) VALUES (?)",basetasks)
        connection.commit()
def get_checklist(connection: sqlite3.Connection):
    """Выдаёт чеклист и процентв выполнения чеклиста
        
            Args:
                connection (sqlite3.Connection): бд
        
            Returns:
                dict: где items - таски
                      progress_percentage - процент выполнения чеклиста
            """
    tasks=[]
    count=0
    currentcount=0
    cursor=connection.cursor()
    cursor.execute("""
                   SELECT id,title,is_completed
                   FROM checklist
                   """)
    for row in cursor.fetchall():
        tasks.append({
            "id": row[0],
            "title":row[1],
            "is_completed": row[2]
        })
        count+=1
        currentcount+=row[2]
    if count==0:
        progress_percentage=0
    else: 
        progress_percentage=round(currentcount/count*100,2)
    return {
        "items":tasks,
        "progress_percentage":progress_percentage
        }
def toggle_item(item_id: int):
    """Меняет значение таски в чек листе
            
                Args:
                    item_id (int): id таски
            
                Returns:
                    bool: где если True,то значение задачи изменилось,а если False, то задача не найдена
                """
    connection=sqlite3.connect("buddy.db")
    cursor=connection.cursor()
    cursor.execute("""
                   UPDATE checklist
                   SET is_completed = NOT is_completed
                   WHERE id=?
                   """,(item_id,))
    win=cursor.rowcount>0
    connection.commit()
    return win
def init_checklist_db():
    """Инициализация чеклиста
                    """
    connection=sqlite3.connect("buddy.db")
    seed_checklist(connection)
    