import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# --- ПОЛУЧЕНИЕ ДАННЫХ ---

def get_room(slug):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM rooms WHERE slug = %s", (slug,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res

def get_data(table, room_id, order_by="id"):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # Сохраняем твою проверку валидности таблиц
    valid_tables = ["profiles", "exercise_types", "games_presets", "workout_logs"]
    if table not in valid_tables: 
        return []
    
    if table == "workout_logs":
        query = """
            SELECT wl.*, p.name as profile_name 
            FROM workout_logs wl
            LEFT JOIN profiles p ON wl.profile_id = p.id
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

def get_ex_type(name, room_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT unit_type FROM exercise_types WHERE name = %s AND room_id = %s", (name, room_id))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else 'amount'

def get_profile_name(p_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM profiles WHERE id = %s", (p_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else "Кто-то"

# --- ДОБАВЛЕНИЕ ДАННЫХ ---

def create_room(slug, title, password, tg_chat_id=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO rooms (slug, title, password, tg_chat_id) VALUES (%s, %s, %s, %s)",
            (slug, title, password, tg_chat_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def add_game_preset(room_id, game_name, ex_name, val, unit_type):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO games_presets (room_id, game_name, ex_name, val, unit_type) 
        VALUES (%s, %s, %s, %s, %s)
    """, (room_id, game_name, ex_name, val, unit_type))
    conn.commit()
    cur.close()
    conn.close()

def add_exercise_type(room_id, name, unit_type):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO exercise_types (room_id, name, unit_type) VALUES (%s, %s, %s)", 
                (room_id, name, unit_type))
    conn.commit()
    cur.close()
    conn.close()

def add_profile(room_id, name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO profiles (room_id, name) VALUES (%s, %s)", (room_id, name))
    conn.commit()
    cur.close()
    conn.close()

def add_log(p_id, ex_name, amount, room_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO workout_logs (profile_id, exercise_type, amount, room_id) VALUES (%s, %s, %s, %s)",
        (p_id, ex_name, amount, room_id)
    )
    conn.commit()
    cur.close()
    conn.close()

# --- УДАЛЕНИЕ ДАННЫХ (УСИЛЕННАЯ ЛОГИКА) ---

def delete_game_preset(id_val):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM games_presets WHERE id = %s", (id_val,))
        conn.commit()
    finally:
        cur.close()
        conn.close()

def delete_exercise_type(id_val, room_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Получаем имя упражнения, чтобы найти зависимости в других таблицах
        cur.execute("SELECT name FROM exercise_types WHERE id = %s AND room_id = %s", (id_val, room_id))
        res = cur.fetchone()
        if res:
            ex_name = res[0]
            # 2. Удаляем связанные логи и пресеты игр (чтобы не было ForeignKeyViolation)
            cur.execute("DELETE FROM workout_logs WHERE exercise_type = %s AND room_id = %s", (ex_name, room_id))
            cur.execute("DELETE FROM games_presets WHERE ex_name = %s AND room_id = %s", (ex_name, room_id))
            # 3. Теперь удаляем само упражнение
            cur.execute("DELETE FROM exercise_types WHERE id = %s", (id_val,))
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error deleting exercise: {e}")
    finally:
        cur.close()
        conn.close()

def delete_profile(id_val, room_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Удаляем сначала логи этого участника
        cur.execute("DELETE FROM workout_logs WHERE profile_id = %s AND room_id = %s", (id_val, room_id))
        # 2. Удаляем сам профиль
        cur.execute("DELETE FROM profiles WHERE id = %s AND room_id = %s", (id_val, room_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error deleting profile: {e}")
    finally:
        cur.close()
        conn.close()

def delete_last_log(room_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            DELETE FROM workout_logs 
            WHERE id = (
                SELECT id FROM workout_logs 
                WHERE room_id = %s 
                ORDER BY created_at DESC 
                LIMIT 1
            )
        """, (room_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error deleting last log: {e}")
    finally:
        cursor.close()
        conn.close()
