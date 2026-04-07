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
    t_str = str(t_str).strip()
    try:
        if ":" in t_str:
            parts = t_str.split(":")
            if len(parts) == 2:
                m, s = map(int, parts)
                return m * 60 + s
        return int(t_str)
    except: return None # Возвращаем None для проверки ошибок

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
    ex_icons = {ex['name']: ("🕒" if ex['unit_type'] == 'time' else "💪") for ex in ex_types}

    for l in logs:
        name, ex, amt = l['profile_name'], l['exercise_type'], l['amount']
        summary.setdefault(name, {}).setdefault(ex, 0)
        summary[name][ex] += amt

    is_admin = session.get(f"auth_{room['room_id']}")
    last_log = logs[0] if logs else None 
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
                           ex_icons=ex_icons,
                           is_admin=is_admin,
                           last_action_text=last_action_text)

@website.route('/add_game', methods=['POST'])
def add_game():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        name = request.form.get('name', '').strip()
        ex_name = request.form.get('ex_name')
        val_raw = request.form.get('val', '').strip()
        
        u_type = db.get_ex_type(ex_name, room['room_id'])
        val_numeric = time_to_seconds(val_raw)

        if val_numeric is None:
            flash(f"Ошибка: Некорректное значение '{val_raw}'. Введите число или ММ:СС")
            return redirect(url_for('index', room=slug))

        # Проверка на дубликаты игр
        existing = db.get_data("games_presets", room['room_id'])
        if any(g['game_name'].lower() == name.lower() for g in existing):
            flash("Ошибка: Такая игра уже есть!")
            return redirect(url_for('index', room=slug))

        db.add_game_preset(room['room_id'], name, ex_name, val_numeric, u_type)
    return redirect(url_for('index', room=slug))

@website.route('/add_exercise', methods=['POST'])
def add_exercise():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        name = request.form.get('name', '').strip()
        u_type = request.form.get('unit_type')
        if name:
            existing = db.get_data("exercise_types", room['room_id'])
            if any(ex['name'].lower() == name.lower() for ex in existing):
                flash("Ошибка: Такое упражнение уже есть!")
            else:
                db.add_exercise_type(room['room_id'], name, u_type)
        else: flash("Название не может быть пустым")
    return redirect(url_for('index', room=slug))

@website.route('/add_profile', methods=['POST'])
def add_profile():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        name = request.form.get('name', '').strip()
        if name:
            existing = db.get_data("profiles", room['room_id'])
            if any(p['name'].lower() == name.lower() for p in existing):
                flash("Ошибка: Пользователь с таким именем уже существует!")
            else:
                db.add_profile(room['room_id'], name)
        else: flash("Имя не может быть пустым")
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
    if not room or not session.get(f"auth_{room['room_id']}"): return "403", 403
    
    p_id = request.form.get('profile_id')
    ex_name = request.form.get('ex_name')
    val_raw = request.form.get('value', '').strip()
    action_type = request.form.get('action_type') 
    
    ex_type_info = db.get_ex_type(ex_name, room['room_id'])
    amt = time_to_seconds(val_raw)
    
    if amt is None:
        flash("Ошибка: Введите корректное число или время (ММ:СС)")
        return redirect(url_for('index', room=slug))

    final_amt = -amt if action_type == 'writeoff' else amt
    db.add_log(p_id, ex_name, final_amt, room['room_id'])
    
    p_name = db.get_profile_name(p_id)
    action_txt = "списал(а)" if action_type == 'writeoff' else "получил(а) долг"
    send_tg_notification(room, f"⚖️ {p_name} {action_txt}: {ex_name} ({val_raw})")
    return redirect(url_for('index', room=slug))

@website.route('/play_game', methods=['POST'])
def play_game():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if not room or not session.get(f"auth_{room['room_id']}"): return "403", 403
    
    game_name = request.form.get('game_name')
    winner_ids = request.form.getlist('winner_ids') # Список ID победителей
    
    # Получаем инфо об игре
    games = db.get_data("games_presets", room['room_id'])
    game = next((g for g in games if g['game_name'] == game_name), None)
    
    if not game or not winner_ids:
        flash("Ошибка: Выберите игру и победителей")
        return redirect(url_for('index', room=slug))

    # Раздаем долги всем профилям, КРОМЕ победителей
    all_profiles = db.get_data("profiles", room['room_id'])
    losers_names = []
    
    for p in all_profiles:
        if str(p['id']) not in winner_ids:
            # Превращаем значение в int, чтобы избежать ошибки "str and int"
            val_to_add = int(game['val']) 
            db.add_log(p['id'], game['ex_name'], val_to_add, room['room_id'])
            losers_names.append(p['name'])
    
    if losers_names:
        msg = f"🎮 Игра: {game_name}\n💀 Проиграли и получили долг ({game['val']}): {', '.join(losers_names)}"
        send_tg_notification(room, msg)
        
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
    title = request.form.get('title', '').strip()
    slug = request.form.get('slug', '').strip()
    password = request.form.get('password')
    tg_id = request.form.get('tg_id', '').strip()
    if not title or not slug:
        flash("Название и адрес обязательны")
        return redirect(url_for('index'))
    try:
        db.create_room(slug, title, password, tg_id if tg_id else None)
        return redirect(f"/{slug}")
    except:
        flash("Ошибка: Адрес занят")
        return redirect(url_for('index'))

if __name__ == '__main__':
    website.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
