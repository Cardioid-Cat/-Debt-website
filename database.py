import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# --- ИНИЦИАЛИЗАЦИЯ (добавление "🏆 Победа" во все комнаты) ---

def ensure_hall_of_fame_exercise(room_id):
    """Добавляет упражнение '🏆 Победа' в комнату, если его ещё нет"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM exercise_types WHERE room_id = %s AND name = '🏆 Победа'",
            (room_id,)
        )
        exists = cur.fetchone()
        if not exists:
            cur.execute(
                "INSERT INTO exercise_types (room_id, name, unit_type) VALUES (%s, %s, %s)",
                (room_id, '🏆 Победа', 'amount')
            )
            conn.commit()
    finally:
        cur.close()
        conn.close()

def init_all_rooms():
    """При запуске приложения добавляет '🏆 Победа' во все существующие комнаты"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT room_id FROM rooms")
        rooms = cur.fetchall()
        for (room_id,) in rooms:
            ensure_hall_of_fame_exercise(room_id)
    finally:
        cur.close()
        conn.close()

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

# --- ДОБАВЛЕНИЕ ДАННЫХ (с проверками) ---

def create_room(slug, title, password, tg_chat_id=None):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO rooms (slug, title, password, tg_chat_id) VALUES (%s, %s, %s, %s)",
            (slug, title, password, tg_chat_id)
        )
        conn.commit()
        # Получаем room_id только что созданной комнаты
        cur.execute("SELECT room_id FROM rooms WHERE slug = %s", (slug,))
        room_id = cur.fetchone()[0]
        # Автоматически добавляем упражнение "🏆 Победа"
        ensure_hall_of_fame_exercise(room_id)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def game_preset_exists(room_id, ex_name, val):
    """Проверяет, есть ли уже игра с таким же упражнением и значением"""
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

def add_game_preset(room_id, game_name, ex_name, val):
    """Добавляет игру, если нет дубликата по (ex_name, val)"""
    if game_preset_exists(room_id, ex_name, val):
        return False  # игра с таким наказанием уже существует
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO games_presets (room_id, game_name, ex_name, val) 
        VALUES (%s, %s, %s, %s)
    """, (room_id, game_name, ex_name, val))
    conn.commit()
    cur.close()
    conn.close()
    return True

def exercise_type_exists(room_id, name):
    """Проверяет, есть ли уже упражнение с таким названием в комнате"""
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
    """Добавляет упражнение, если нет дубликата по имени и это не служебное '🏆 Победа'"""
    if name == "🏆 Победа":
        return False  # запрещаем ручное создание
    if exercise_type_exists(room_id, name):
        return False
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO exercise_types (room_id, name, unit_type) VALUES (%s, %s, %s)",
        (room_id, name, unit_type)
    )
    conn.commit()
    cur.close()
    conn.close()
    return True

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

# --- УДАЛЕНИЕ ДАННЫХ (с защитой "🏆 Победа") ---

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
        # Получаем имя упражнения
        cur.execute("SELECT name FROM exercise_types WHERE id = %s AND room_id = %s", (id_val, room_id))
        res = cur.fetchone()
        if res:
            ex_name = res[0]
            if ex_name == "🏆 Победа":
                # Не удаляем служебное упражнение
                return False
            # Удаляем связанные логи и пресеты
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
