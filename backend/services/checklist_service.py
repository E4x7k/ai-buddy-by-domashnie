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
                           is_complete INTEGER DEFAULT 0
                       )
                       """)
    cursor.execute("SELECT COUNT(*) FROM checklist")
    if cursor.fetchone()[0]==0:
        basetasks=[
            ("Познакомится с командой",),
                   ("Изучи все необходимые документы и мануалы по работе в своей команде/вертикали/кластеру, которыми с тобой поделился бадди/руководитель",),
                   ("Изучи основы защиты персональных данных и другие инструкции Авито",),
                   ("Изучи памятку, как закрывать практику, писать учебные работы по Авито",),
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
                   SELECT id,title,is_complete
                   FROM checklist
                   """)
    for row in cursor.fetchall():
        tasks.append({
            "id": row[0],
            "title":row[1],
            "is_complete": row[2]
        })
        count+=1
        currentcount+=row[2]
    progress_percentage=int(currentcount/count*100)
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
    connection=sqlite3.connect("database.db")
    cursor=connection.cursor()
    cursor.execute("""
                   UPDATE checklist
                   SET is_complete = NOT is_complete
                   WHERE id=?
                   """,(item_id,))
    win=cursor.rowcount>0
    connection.commit()
    return win
def init_checklist_db():
    """Инициализация чеклиста
                    """
    connection=sqlite3.connect("database.db")
    seed_checklist(connection)
    