import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Ссылка на базу из настроек Railway
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    # Подключение к PostgreSQL в Railway с поддержкой SSL
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# --- 1. ЛОГИКА КОМНАТ (СОЗДАНИЕ И ПОИСК) ---
def get_room(slug):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM rooms WHERE slug = %s", (slug,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res

def create_room(slug, title, password, tg_token=None, tg_chat_id=None):
    """Создание новой комнаты с привязкой бота сразу"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO rooms (slug, title, password, tg_token, tg_chat_id) 
           VALUES (%s, %s, %s, %s, %s)""",
        (slug, title, password, tg_token, tg_chat_id)
    )
    conn.commit()
    cur.close()
    conn.close()

# --- 2. ПОЛУЧЕНИЕ ВСЕХ ДАННЫХ КОМНАТЫ ---
def get_data(table, room_id, order_by="id"):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Безопасная проверка имен таблиц
    valid_tables = ["profiles", "exercise_types", "games_presets", "workout_logs"]
    if table not in valid_tables:
        return []
    
    if table == "workout_logs":
        # Для логов подтягиваем имя участника через JOIN, чтобы не делать лишних запросов
        query = """
            SELECT wl.*, p.name as profile_name 
            FROM workout_logs wl
            JOIN profiles p ON wl.profile_id = p.id
            WHERE wl.room_id = %s 
            ORDER BY wl.created_at DESC
        """
        cur.execute(query, (room_id,))
    else:
        query = f"SELECT * FROM {table} WHERE room_id = %s ORDER BY {order_by}"
        cur.execute(query, (room_id,))
    
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

# --- 3. РЕДАКТИРОВАНИЕ (ДОБАВЛЕНИЕ И УДАЛЕНИЕ) ---
def add_entity(table, data):
    """Универсальное добавление участников, упражнений и игр"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    if table == "profiles":
        cur.execute("INSERT INTO profiles (name, room_id) VALUES (%s, %s)", 
                    (data['name'], data['room_id']))
    elif table == "exercise_types":
        cur.execute("INSERT INTO exercise_types (name, unit_type, room_id) VALUES (%s, %s, %s)", 
                    (data['name'], data['unit_type'], data['room_id']))
    elif table == "games_presets":
        cur.execute("""
            INSERT INTO games_presets (game_name, ex_name, val, unit_type, room_id) 
            VALUES (%s, %s, %s, %s, %s)
        """, (data['game_name'], data['ex_name'], data['val'], data['unit_type'], data['room_id']))
        
    conn.commit()
    cur.close()
    conn.close()

def delete_entity(table, entity_id):
    """Удаление по ID. Благодаря ON DELETE CASCADE в SQL, 
    при удалении профиля его логи удалятся сами."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {table} WHERE id = %s", (entity_id,))
    conn.commit()
    cur.close()
    conn.close()

# --- 4. РАБОТА С ЛОГАМИ (ДОЛГИ И СПИСАНИЯ) ---
def add_log(p_id, ex_name, amount, room_id):
    """Добавляет запись тренировки (положительный amount - долг, отрицательный - списание)"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO workout_logs (profile_id, exercise_type, amount, room_id) VALUES (%s, %s, %s, %s)",
        (p_id, ex_name, amount, room_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_ex_type(name, room_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT unit_type FROM exercise_types WHERE name = %s AND room_id = %s", (name, room_id))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else 'count'

def get_profile_name(p_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM profiles WHERE id = %s", (p_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else "Кто-то"
