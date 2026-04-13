import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# --- БЕЗОПАСНОЕ ДОБАВЛЕНИЕ "🏆 Победа" (без ошибок дубликата) ---

def ensure_hall_of_fame_exercise(room_id):
    """Добавляет упражнение '🏆 Победа' в комнату, если его ещё нет.
       Использует WHERE NOT EXISTS, чтобы избежать конфликтов с уникальным ограничением."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO exercise_types (room_id, name, unit_type)
            SELECT %s, %s, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM exercise_types 
                WHERE room_id = %s AND name = %s
            )
        """, (room_id, '🏆 Победа', 'amount', room_id, '🏆 Победа'))
        conn.commit()
    except Exception as e:
        print(f"ensure_hall_of_fame_exercise error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# --- ПОЛУЧЕНИЕ ДАННЫХ ---

def get_room(slug):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM rooms WHERE slug = %s", (slug,))
    room = cur.fetchone()
    cur.close()
    conn.close()
    if room:
        ensure_hall_of_fame_exercise(room['room_id'])
    return room

def get_data(table, room_id, order_by="id"):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
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

# --- ДОБАВЛЕНИЕ (с проверками дубликатов) ---

def create_room(slug, title, password, tg_chat_id=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO rooms (slug, title, password, tg_chat_id) VALUES (%s, %s, %s, %s)",
            (slug, title, password, tg_chat_id)
        )
        conn.commit()
        cur.execute("SELECT room_id FROM rooms WHERE slug = %s", (slug,))
        room_id = cur.fetchone()[0]
        ensure_hall_of_fame_exercise(room_id)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def game_preset_exists(room_id, ex_name, val):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM games_presets WHERE room_id = %s AND ex_name = %s AND val = %s",
        (room_id, ex_name, val)
    )
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists

def game_name_exists(room_id, game_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM games_presets WHERE room_id = %s AND game_name = %s",
        (room_id, game_name)
    )
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists

def add_game_preset(room_id, game_name, ex_name, val, unit_type):
    if game_name_exists(room_id, game_name):
        return False, "Игра с таким названием уже существует"
    if game_preset_exists(room_id, ex_name, val):
        return False, "Игра с таким наказанием уже существует"
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO games_presets (room_id, game_name, ex_name, val, unit_type) 
            VALUES (%s, %s, %s, %s, %s)
        """, (room_id, game_name, ex_name, val, unit_type))
        conn.commit()
        return True, None
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()

def exercise_type_exists(room_id, name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM exercise_types WHERE room_id = %s AND name = %s",
        (room_id, name)
    )
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists

def add_exercise_type(room_id, name, unit_type):
    if name == "🏆 Победа":
        return False
    name = name.strip()
    if exercise_type_exists(room_id, name):
        return False
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO exercise_types (room_id, name, unit_type) VALUES (%s, %s, %s)",
            (room_id, name, unit_type)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error adding exercise: {e}")
        return False
    finally:
        cur.close()
        conn.close()

def profile_exists(room_id, name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM profiles WHERE room_id = %s AND name = %s", (room_id, name))
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists

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

# --- УДАЛЕНИЕ (с защитой "🏆 Победа") ---

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
        cur.execute("SELECT name FROM exercise_types WHERE id = %s AND room_id = %s", (id_val, room_id))
        res = cur.fetchone()
        if res:
            ex_name = res[0]
            if ex_name == "🏆 Победа":
                return False
            cur.execute("DELETE FROM workout_logs WHERE exercise_type = %s AND room_id = %s", (ex_name, room_id))
            cur.execute("DELETE FROM games_presets WHERE ex_name = %s AND room_id = %s", (ex_name, room_id))
            cur.execute("DELETE FROM exercise_types WHERE id = %s", (id_val,))
            conn.commit()
            return True
        return False
    except Exception as e:
        conn.rollback()
        print(f"Error deleting exercise: {e}")
        return False
    finally:
        cur.close()
        conn.close()

def delete_profile(id_val, room_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM workout_logs WHERE profile_id = %s AND room_id = %s", (id_val, room_id))
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
        
# === РАБОТА С УЧАСТНИКАМИ ГРУПП ДЛЯ УПОМИНАНИЙ ===

def get_group_members(chat_id: int):
    """Возвращает список user_id участников Telegram-группы."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM group_members WHERE chat_id = %s", (chat_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [row[0] for row in rows]
