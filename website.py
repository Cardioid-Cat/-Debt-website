import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import database as db
import requests

website = Flask(__name__)
website.secret_key = os.environ.get("FLASK_SECRET_KEY", "vova_top_secret_777")

def send_tg_notification(room, text):
    """Отправляет сообщение в Telegram-группу комнаты с упоминанием всех участников (скрытые упоминания)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = room.get("tg_chat_id")
    if not token or not chat_id:
        return
    try:
        members = db.get_group_members(int(chat_id))
        if members:
            mentions = "".join([f'<a href="tg://user?id={uid}">\u2060</a>' for uid in members])
            full_text = f"{mentions}\n{text}"
        else:
            full_text = f"📢 @all\n{text}"
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": full_text, "parse_mode": "HTML"},
            timeout=5
        )
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

def time_to_seconds(t_str):
    """Преобразует строку в секунды. Поддерживает число или ММ:СС. Возвращает None при ошибке."""
    t_str = str(t_str).strip()
    if not t_str:
        return None
    try:
        if ":" in t_str:
            parts = t_str.split(":")
            if len(parts) == 2:
                m, s = map(int, parts)
                return m * 60 + s
            else:
                return None
        else:
            return int(t_str)
    except:
        return None

@website.route('/')
@website.route('/<slug>')
def index(slug=None):
    if not slug: slug = request.args.get('room')
    if not slug: return render_template('create_room.html')
    
    room = db.get_room(slug)
    if not room: return "Ошибка: Комната не найдена", 404
    
    room_actual_id = room['room_id']
    profiles = db.get_data("profiles", room_actual_id)
    ex_types = db.get_data("exercise_types", room_actual_id)
    games = db.get_data("games_presets", room_actual_id)
    logs = db.get_data("workout_logs", room_actual_id)
    
    summary = {p['name']: {} for p in profiles}
    id_to_name = {p['id']: p['name'] for p in profiles}
    ex_map = {ex['name']: ex['unit_type'] for ex in ex_types}
    ex_icons = {ex['name']: ("🕒" if ex['unit_type'] == 'time' else "💪") for ex in ex_types}

    hof_data = {}
    for l in logs:
        if l.get('exercise_type') == "🏆 Победа":
            p_id = l.get('profile_id')
            name = id_to_name.get(p_id) or l.get('profile_name', 'Кто-то')
            hof_data[name] = hof_data.get(name, 0) + 1
    
    hall_of_fame = [{"name": k, "wins": v} for k, v in hof_data.items()]
    hall_of_fame.sort(key=lambda x: x['wins'], reverse=True)

    for l in logs:
        if l.get('exercise_type') == "🏆 Победа": continue
        p_id = l.get('profile_id')
        p_name_in_log = l.get('profile_name')
        name = id_to_name.get(p_id) or p_name_in_log
        if name in summary:
            ex = l['exercise_type']
            amt = l['amount']
            summary[name].setdefault(ex, 0)
            summary[name][ex] += amt

    is_admin = session.get(f"auth_{room['room_id']}")
    last_log = logs[0] if logs else None
    last_action_text = ""
    if last_log:
        p_act_name = id_to_name.get(last_log.get('profile_id')) or last_log.get('profile_name', 'Кто-то')
        last_action_text = f"Последнее: {p_act_name} - {last_log['exercise_type']}"

    return render_template('index.html', room=room, profiles=profiles, ex_types=ex_types, 
                           games=games, summary=summary, ex_map=ex_map, 
                           ex_icons=ex_icons, is_admin=is_admin, last_action_text=last_action_text,
                           hall_of_fame=hall_of_fame)

@website.route('/add_game', methods=['POST'])
def add_game():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if not room or not session.get(f"auth_{room['room_id']}"):
        return redirect(url_for('index', room=slug))
    
    name = request.form.get('name', '').strip()
    ex_name = request.form.get('ex_name')
    val_raw = request.form.get('val', '').strip()
    
    if not name or not ex_name or not val_raw:
        flash("Заполните все поля")
        return redirect(url_for('index', room=slug))
    
    unit_type = db.get_ex_type(ex_name, room['room_id'])
    val_numeric = time_to_seconds(val_raw)
    if val_numeric is None:
        flash("Некорректный формат наказания. Используйте число или ММ:СС (например, 1:30)")
        return redirect(url_for('index', room=slug))
    
    if unit_type == 'amount' and ':' in val_raw:
        flash("Для упражнения на количество нельзя использовать формат ММ:СС. Введите число.")
        return redirect(url_for('index', room=slug))
    
    if db.game_name_exists(room['room_id'], name):
        flash(f"Игра с названием «{name}» уже существует в этой комнате.")
        return redirect(url_for('index', room=slug))
    
    if db.game_preset_exists(room['room_id'], ex_name, val_numeric):
        flash(f"Игра с наказанием '{ex_name} {val_raw}' уже существует!")
        return redirect(url_for('index', room=slug))
    
    success, err_msg = db.add_game_preset(room['room_id'], name, ex_name, val_numeric, unit_type)
    if success:
        flash(f"Игра «{name}» добавлена")
    else:
        flash(f"Ошибка: {err_msg}")
    
    return redirect(url_for('index', room=slug))

@website.route('/add_exercise', methods=['POST'])
def add_exercise():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        name = request.form.get('name', '').strip()
        u_type = request.form.get('unit_type')
        if name:
            if name == "🏆 Победа":
                flash("Нельзя создать упражнение «🏆 Победа» – оно создаётся автоматически.")
            elif db.exercise_type_exists(room['room_id'], name):
                flash(f"Упражнение «{name}» уже существует в этой комнате.")
            else:
                success = db.add_exercise_type(room['room_id'], name, u_type)
                if success:
                    flash(f"Упражнение «{name}» добавлено.")
                else:
                    flash(f"Не удалось добавить упражнение «{name}». Возможно, оно уже существует.")
        else:
            flash("Название упражнения не может быть пустым.")
    return redirect(url_for('index', room=slug))

@website.route('/add_profile', methods=['POST'])
def add_profile():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        name = request.form.get('name', '').strip()
        if name:
            if db.profile_exists(room['room_id'], name):
                flash("Участник с таким именем уже существует в этой комнате.")
            else:
                db.add_profile(room['room_id'], name)
    return redirect(url_for('index', room=slug))

@website.route('/delete_<type>/<id_val>')
def delete_item(type, id_val):
    slug = request.args.get('slug')
    room = db.get_room(slug)
    if room and session.get(f"auth_{room['room_id']}"):
        if type == 'game': 
            db.delete_game_preset(id_val)
        elif type == 'ex': 
            if not db.delete_exercise_type(id_val, room['room_id']):
                flash("Нельзя удалить служебное упражнение «🏆 Победа».")
        elif type == 'profile': 
            db.delete_profile(id_val, room['room_id'])
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
    amt = time_to_seconds(val_raw)
    if amt is not None:
        final_amt = -amt if action_type == 'writeoff' else amt
        db.add_log(p_id, ex_name, final_amt, room['room_id'])
        p_name = db.get_profile_name(p_id)
        action_txt = "списал(а)" if action_type == 'writeoff' else "получил(а) долг"
        send_tg_notification(room, f"⚖️ {p_name} {action_txt}: {ex_name} ({val_raw})")
    else:
        flash("Некорректное значение")
    return redirect(url_for('index', room=slug))

@website.route('/play_game', methods=['POST'])
def play_game():
    slug = request.form.get('slug')
    room = db.get_room(slug)
    if not room or not session.get(f"auth_{room['room_id']}"):
        return "403", 403
    game_name = request.form.get('game_name')
    winner_ids = request.form.getlist('winner_ids')
    games = db.get_data("games_presets", room['room_id'])
    game = next((g for g in games if g['game_name'] == game_name), None)
    if game and winner_ids:
        try:
            all_profiles = db.get_data("profiles", room['room_id'])
            losers_names = []
            for p in all_profiles:
                p_id_str = str(p['id'])
                if p_id_str not in winner_ids:
                    db.add_log(p['id'], game['ex_name'], game['val'], room['room_id'])
                    losers_names.append(p['name'])
                else:
                    db.add_log(p['id'], "🏆 Победа", 1, room['room_id'])
            
            if losers_names:
                exercise_name = game['ex_name']
                val_display = game['val']
                if game['unit_type'] == 'time':
                    minutes = val_display // 60
                    seconds = val_display % 60
                    val_display = f"{minutes}:{seconds:02d}"
                msg = f"🎮 Игра: {game_name}\n💀 Проиграли: {', '.join(losers_names)} (+{val_display} {exercise_name})"
                send_tg_notification(room, msg)
        except Exception as e:
            flash(f"Ошибка при обработке игры: {e}")
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
    if title and slug:
        try:
            db.create_room(slug, title, password, tg_id if tg_id else None)
            return redirect(f"/{slug}")
        except: flash("Ошибка: Адрес занят")
    return redirect(url_for('index'))

if __name__ == '__main__':
    website.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
