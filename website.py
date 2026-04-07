import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import database as db
import requests

website = Flask(__name__)
# Секретный ключ для работы сессий (авторизации)
website.secret_key = os.environ.get("FLASK_SECRET_KEY", "vova_top_secret_777")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (перенесены из твоего кода) ---

def send_tg_notification(room, text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = room.get("tg_chat_id")
    if not token or not chat_id: return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      json={"chat_id": chat_id, "text": f"📢 @all ({room['title']})\n{text}"}, timeout=5)
    except: pass

def time_to_seconds(t_str):
    try:
        if ":" in str(t_str):
            m, s = map(int, str(t_str).split(":"))
            return m * 60 + s
        return int(t_str)
    except: return 0

def seconds_to_str(sec):
    m, s = abs(int(sec)) // 60, abs(int(sec)) % 60
    return f"{'-' if int(sec) < 0 else ''}{m}:{s:02d}"

# --- ОСНОВНЫЕ МАРШРУТЫ ---

@website.route('/')
def index():
    slug = request.args.get('room')
    # Если комната не указана — показываем страницу создания (регистрации)
    if not slug:
        return render_template('create_room.html')
    
    room = db.get_room(slug)
    if not room:
        return "Ошибка: Комната не найдена", 404
    
    # Загружаем данные из БД через твой database.py
    profiles = db.get_data("profiles", room['id'])
    ex_types = db.get_data("exercise_types", room['id'])
    games = db.get_data("games_presets", room['id'])
    logs = db.get_data("workout_logs", room['id'])
    
    # Обработка долгов для отображения (как в твоем старом коде)
    summary = {}
    ex_map = {ex['name']: ex['unit_type'] for ex in ex_types}
    for l in logs:
        if "🏆" in l['exercise_type']: continue
        name, ex, amt = l['profile_name'], l['exercise_type'], l['amount']
        summary.setdefault(name, {}).setdefault(ex, 0)
        summary[name][ex] += amt

    # Проверяем, залогинен ли админ именно в ЭТУ комнату
    is_admin = session.get(f"auth_{room['id']}")

    return render_template('index.html', 
                           room=room, 
                           profiles=profiles, 
                           ex_types=ex_types, 
                           games=games, 
                           summary=summary, 
                           ex_map=ex_map, 
                           is_admin=is_admin)

@website.route('/create_room', methods=['POST'])
def handle_create_room():
    title = request.form.get('title', '').strip()
    slug = request.form.get('slug', '').lower().strip()
    password = request.form.get('password', '').strip()
    tg_id = request.form.get('tg_id', '').strip()
    
    # ПРОВЕРКА: если после удаления пробелов поля пустые
    if not title or not slug or not password:
        flash("⚠️ Поля 'Название', 'Адрес' и 'Пароль' не могут быть пустыми или состоять только из пробелов!")
        return redirect(url_for('index'))
    
    try:
        db.create_room(slug, title, password, tg_id if tg_id else None)
        return redirect(url_for('index', room=slug))
    except Exception as e:
        flash(f"Ошибка: Адрес '{slug}' уже занят или база недоступна.")
        return redirect(url_for('index'))

@website.route('/login', methods=['POST'])
def login():
    slug = request.form.get('slug')
    password = request.form.get('password')
    room = db.get_room(slug)
    if room and room['password'] == password:
        session[f"auth_{room['id']}"] = True
    else:
        flash("Неверный пароль")
    return redirect(url_for('index', room=slug))

@website.route('/add_log', methods=['POST'])
def add_log():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if not session.get(f"auth_{room['id']}"): 
        return "Доступ запрещен", 403
    
    p_id = request.form.get('profile_id')
    ex_name = request.form.get('ex_name')
    val = request.form.get('value')
    is_writeoff = 'writeoff' in request.form
    
    # Логика конвертации (из твоего кода)
    ex_type_info = db.get_ex_type(ex_name, room['id'])
    is_time = (ex_type_info == 'time')
    
    amt = time_to_seconds(val) if is_time else int(val)
    final_amt = -amt if is_writeoff else amt
    
    db.add_log(p_id, ex_name, final_amt, room['id'])
    
    # Уведомление в ТГ
    p_name = db.get_profile_name(p_id)
    action = "списал(а)" if is_writeoff else "получил(а) долг"
    send_tg_notification(room, f"⚖️ {p_name} {action}: {ex_name} ({val})")
    
    return redirect(url_for('index', room=slug))

if __name__ == '__main__':
    # Railway сам назначит порт через переменную окружения
    port = int(os.environ.get("PORT", 5000))
    website.run(host='0.0.0.0', port=port)
