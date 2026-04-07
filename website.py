import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import database as db
import requests

website = Flask(__name__)
website.secret_key = os.environ.get("FLASK_SECRET_KEY", "vova_top_secret_777")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (без изменений) ---

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
@website.route('/<slug>')
def index(slug=None):
    if not slug:
        slug = request.args.get('room')
    
    if not slug:
        return render_template('create_room.html')
    
    room = db.get_room(slug)
    if not room:
        return "Ошибка: Комната не найдена", 404
    
    room_actual_id = room['room_id'] 
    
    profiles = db.get_data("profiles", room_actual_id)
    ex_types = db.get_data("exercise_types", room_actual_id)
    games = db.get_data("games_presets", room_actual_id)
    logs = db.get_data("workout_logs", room_actual_id)
    
    summary = {}
    ex_map = {ex['name']: ex['unit_type'] for ex in ex_types}
    for l in logs:
        if "🏆" in l['exercise_type']: continue
        name, ex, amt = l['profile_name'], l['exercise_type'], l['amount']
        summary.setdefault(name, {}).setdefault(ex, 0)
        summary[name][ex] += amt

    is_admin = session.get(f"auth_{room['room_id']}")

    # Достаем последнее действие для кнопки "Отменить"
    last_log = logs[-1] if logs else None
    last_action_text = ""
    if last_log:
        last_action_text = f"Последнее: {last_log['profile_name']} - {last_log['exercise_type']}"

    return render_template('index.html', 
                           room=room, 
                           profiles=profiles, 
                           ex_types=ex_types, 
                           games=games, 
                           summary=summary, 
                           ex_map=ex_map, 
                           is_admin=is_admin,
                           last_action_text=last_action_text)

# --- НОВЫЕ МАРШРУТЫ ДЛЯ КНОПОК МЕНЮ ---

@website.route('/logout')
def logout():
    slug = request.args.get('slug')
    room = db.get_room(slug)
    if room:
        session.pop(f"auth_{room['room_id']}", None)
    return redirect(url_for('index', room=slug))

@website.route('/undo/<slug>')
def undo(slug):
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        db.delete_last_log(room['room_id'])
        send_tg_notification(room, "🔙 Последнее действие было отменено админом.")
    return redirect(url_for('index', room=slug))

@website.route('/settings/<type>/<slug>')
def settings_page(type, slug):
    room = db.get_room(slug)
    if not room or not session.get(f"auth_{room['room_id']}"):
        return redirect(url_for('index', room=slug))
    
    # Здесь ты можешь отрендерить отдельные шаблоны для настроек
    # Или один общий settings.html
    return f"Страница настройки {type} для комнаты {slug} в разработке"

# --- ОБРАБОТКА ДАННЫХ (add_log дополнен) ---

@website.route('/add_log', methods=['POST'])
def add_log():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    
    if not room or not session.get(f"auth_{room['room_id']}"): 
        return "Доступ запрещен", 403
    
    p_id = request.form.get('profile_id')
    ex_name = request.form.get('ex_name')
    val = request.form.get('value')
    # Проверяем action_type из скрытого поля формы
    action_type = request.form.get('action_type') 
    
    ex_type_info = db.get_ex_type(ex_name, room['room_id'])
    is_time = (ex_type_info == 'time')
    
    amt = time_to_seconds(val) if is_time else int(val)
    final_amt = -amt if action_type == 'writeoff' else amt
    
    db.add_log(p_id, ex_name, final_amt, room['room_id'])
    
    p_name = db.get_profile_name(p_id)
    action_txt = "списал(а)" if action_type == 'writeoff' else "получил(а) долг"
    send_tg_notification(room, f"⚖️ {p_name} {action_txt}: {ex_name} ({val})")
    
    return redirect(url_for('index', room=slug))

# --- МАРШРУТЫ СОЗДАНИЯ И ЛОГИНА (без изменений) ---

@website.route('/create_room', methods=['POST'])
def handle_create_room():
    title = request.form.get('title', '').strip()
    slug = request.form.get('slug', '').lower().strip()
    password = request.form.get('password', '').strip()
    tg_id = request.form.get('tg_id', '').strip()
    
    if not title or not slug or not password:
        flash("⚠️ Поля не могут быть пустыми!")
        return redirect(url_for('index'))
    
    try:
        db.create_room(slug, title, password, tg_id if tg_id else None)
        return redirect(f"/{slug}")
    except Exception as e:
        flash(f"Ошибка: Адрес '{slug}' уже занят.")
        return redirect(url_for('index'))

@website.route('/login', methods=['POST'])
def login():
    slug = request.form.get('slug')
    password = request.form.get('password')
    room = db.get_room(slug)
    if room and room['password'] == password:
        session[f"auth_{room['room_id']}"] = True
    else:
        flash("Неверный пароль")
    return redirect(url_for('index', room=slug))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    website.run(host='0.0.0.0', port=port)
