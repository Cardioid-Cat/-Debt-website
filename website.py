import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import database as db
import requests

website = Flask(__name__)
website.secret_key = os.environ.get("FLASK_SECRET_KEY", "vova_top_secret_777")

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
        name, ex, amt = l['profile_name'], l['exercise_type'], l['amount']
        summary.setdefault(name, {}).setdefault(ex, 0)
        summary[name][ex] += amt

    is_admin = session.get(f"auth_{room['room_id']}")
    last_log = logs[0] if logs else None # Т.к. сортировка DESC, первый — последний
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

@website.route('/add_game', methods=['POST'])
def add_game():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        name = request.form.get('name')
        ex_name = request.form.get('ex_name')
        val = request.form.get('val')
        # Ищем тип упражнения
        u_type = db.get_ex_type(ex_name, room['room_id'])
        if name and ex_name:
            db.add_game_preset(room['room_id'], name, ex_name, val, u_type)
    return redirect(url_for('index', room=slug))

@website.route('/add_exercise', methods=['POST'])
def add_exercise():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        name = request.form.get('name')
        u_type = request.form.get('unit_type')
        if name: db.add_exercise_type(room['room_id'], name, u_type)
    return redirect(url_for('index', room=slug))

@website.route('/add_profile', methods=['POST'])
def add_profile():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        name = request.form.get('name')
        if name: db.add_profile(room['room_id'], name)
    return redirect(url_for('index', room=slug))

@website.route('/delete_<type>/<int:id_val>')
def delete_item(type, id_val):
    slug = request.args.get('slug')
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        if type == 'game': db.delete_game_preset(id_val)
        elif type == 'ex': db.delete_exercise_type(id_val)
        elif type == 'profile': db.delete_profile(id_val)
    return redirect(url_for('index', room=slug))

@website.route('/undo/<slug>')
def undo(slug):
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        db.delete_last_log(room['room_id'])
    return redirect(url_for('index', room=slug))

@website.route('/add_log', methods=['POST'])
def add_log():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if not room or not session.get(f"auth_{room['room_id']}"): return "Доступ запрещен", 403
    p_id = request.form.get('profile_id')
    ex_name = request.form.get('ex_name')
    val = request.form.get('value')
    action_type = request.form.get('action_type') 
    ex_type_info = db.get_ex_type(ex_name, room['room_id'])
    amt = time_to_seconds(val) if ex_type_info == 'time' else int(val)
    final_amt = -amt if action_type == 'writeoff' else amt
    db.add_log(p_id, ex_name, final_amt, room['room_id'])
    p_name = db.get_profile_name(p_id)
    action_txt = "списал(а)" if action_type == 'writeoff' else "получил(а) долг"
    send_tg_notification(room, f"⚖️ {p_name} {action_txt}: {ex_name} ({val})")
    return redirect(url_for('index', room=slug))

@website.route('/login', methods=['POST'])
def login():
    slug = request.form.get('slug')
    password = request.form.get('password')
    room = db.get_room(slug)
    if room and room['password'] == password:
        session[f"auth_{room['room_id']}"] = True
    else: flash("Неверный пароль")
    return redirect(url_for('index', room=slug))

@website.route('/logout')
def logout():
    slug = request.args.get('slug')
    room = db.get_room(slug)
    if room: session.pop(f"auth_{room['room_id']}", None)
    return redirect(url_for('index', room=slug))

@website.route('/create_room', methods=['POST'])
def handle_create_room():
    title, slug, password = request.form.get('title'), request.form.get('slug'), request.form.get('password')
    tg_id = request.form.get('tg_id')
    try:
        db.create_room(slug, title, password, tg_id if tg_id else None)
        return redirect(f"/{slug}")
    except:
        flash("Ошибка: Адрес занят")
        return redirect(url_for('index'))

if __name__ == '__main__':
    website.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
