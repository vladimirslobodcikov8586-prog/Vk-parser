import os
import time
import threading
import requests
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# ================= НАСТРОЙКИ И ПЕРЕМЕННЫЕ =================
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
VK_TOKEN = os.getenv("VK_TOKEN")
JSONBIN_BIN_ID = os.getenv("JSONBIN_BIN_ID")
JSONBIN_API_KEY = os.getenv("JSONBIN_API_KEY")
RENDER_URL = os.getenv("RENDER_URL", "https://vk-parser-xhkd.onrender.com")

CHECK_INTERVAL = 300  # 5 минут

DEFAULT_GROUPS = ["kinopoisk", "vtorchermetekb", "barakholka_group_66"]
last_seen_ids = {}

# HTML-шаблон для встроенной админки
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Управление группами ВК</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #121212; color: #e0e0e0; margin: 0; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; background: #1e1e1e; padding: 25px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
        h1 { font-size: 22px; color: #fff; margin-top: 0; text-align: center; }
        .form-group { display: flex; gap: 10px; margin-bottom: 25px; }
        input[type="text"] { flex: 1; padding: 12px 15px; border-radius: 8px; border: 1px solid #333; background: #2a2a2a; color: #fff; font-size: 15px; outline: none; }
        input[type="text"]:focus { border-color: #0088cc; }
        button { padding: 12px 20px; border-radius: 8px; border: none; background: #0088cc; color: white; font-weight: bold; cursor: pointer; transition: background 0.2s; }
        button:hover { background: #006699; }
        .btn-delete { background: #e53935; padding: 6px 12px; font-size: 13px; }
        .btn-delete:hover { background: #c62828; }
        ul { list-style: none; padding: 0; margin: 0; }
        li { display: flex; justify-content: space-between; align-items: center; padding: 12px 15px; background: #2a2a2a; border-radius: 8px; margin-bottom: 10px; }
        .group-name { font-weight: 500; font-size: 16px; color: #64b5f6; text-decoration: none; }
        .group-name:hover { text-decoration: underline; }
        .status { text-align: center; font-size: 13px; color: #888; margin-top: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚙️ Панель управления VK Парсером</h1>
        
        <form action="/add" method="POST" class="form-group">
            <input type="text" name="group" placeholder="Введите ID или ссылку на группу ВК" required>
            <button type="submit">Добавить</button>
        </form>

        <h3>Список отслеживаемых групп:</h3>
        <ul>
            {% for group in groups %}
            <li>
                <a href="https://vk.com/{{ group }}" target="_blank" class="group-name">vk.com/{{ group }}</a>
                <form action="/delete" method="POST" style="margin:0;">
                    <input type="hidden" name="group" value="{{ group }}">
                    <button type="submit" class="btn-delete">Удалить</button>
                </form>
            </li>
            {% endfor %}
        </ul>

        <div class="status">Бот работает в фоновом режиме</div>
    </div>
</body>
</html>
"""

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================
def send_telegram_message(text, photos=None, video_links=None):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("⚠️ Ошибка: TG_TOKEN или TG_CHAT_ID не заданы")
        return

    photos = photos or []
    video_links = video_links or []

    if video_links:
        text += "\n\n🎬 <b>Видео в посте:</b>\n" + "\n".join(video_links)

    caption = text[:1000] + ("..." if len(text) > 1000 else "")

    try:
        if len(photos) == 1:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
            payload = {
                "chat_id": TG_CHAT_ID,
                "photo": photos[0],
                "caption": caption,
                "parse_mode": "HTML"
            }
            requests.post(url, json=payload, timeout=10)
        elif len(photos) > 1:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup"
            media = []
            for idx, photo_url in enumerate(photos[:10]):
                item = {"type": "photo", "media": photo_url}
                if idx == 0:
                    item["caption"] = caption
                    item["parse_mode"] = "HTML"
                media.append(item)
            payload = {"chat_id": TG_CHAT_ID, "media": media}
            requests.post(url, json=payload, timeout=10)
        else:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            payload = {
                "chat_id": TG_CHAT_ID,
                "text": text[:4000],
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

def get_groups():
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
        print("⚠️ Переменные JSONBin не заданы. Используем стандартный список.")
        return list(DEFAULT_GROUPS)

    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
    headers = {"X-Master-Key": JSONBIN_API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            record = res.json().get("record")
            if isinstance(record, list):
                return record
            elif isinstance(record, dict) and "groups" in record:
                return record["groups"]
        print(f"Ошибка JSONBin: Status {res.status_code}")
    except Exception as e:
        print(f"Ошибка загрузки групп из JSONBin: {e}")
    return list(DEFAULT_GROUPS)

def save_groups(groups_list):
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
        return False

    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
    headers = {
        "X-Master-Key": JSONBIN_API_KEY,
        "Content-Type": "application/json"
    }
    try:
        res = requests.put(url, headers=headers, json=groups_list, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Ошибка сохранения групп в JSONBin: {e}")
        return False

def clean_group_name(raw_input):
    group = raw_input.strip().lower()
    if "vk.com/" in group:
        group = group.split("vk.com/")[-1].strip("/")
    if "?" in group:
        group = group.split("?")[0]
    return group

def extract_attachments(attachments_data):
    photos = []
    video_links = []
    for att in attachments_data:
        att_type = att.get("type")
        if att_type == "photo":
            sizes = att.get("photo", {}).get("sizes", [])
            if sizes:
                best_size = max(sizes, key=lambda s: s.get("width", 0) * s.get("height", 0))
                photos.append(best_size["url"])
        elif att_type == "video":
            video_info = att.get("video", {})
            owner_id = video_info.get("owner_id")
            video_id = video_info.get("id")
            title = video_info.get("title", "Смотреть видео")
            if owner_id and video_id:
                v_url = f"https://vk.com/video{owner_id}_{video_id}"
                video_links.append(f"• <a href='{v_url}'>{title}</a>")
                image_sizes = video_info.get("image", [])
                if image_sizes and not photos:
                    best_img = max(image_sizes, key=lambda i: i.get("width", 0))
                    photos.append(best_img["url"])
    return photos, video_links

def check_vk_posts():
    groups = get_groups()
    if not groups:
        print("Список групп пуст.")
        return

    print(f"Проверка постов для групп: {groups}")
    for group in groups:
        if not VK_TOKEN:
            print("⚠️ VK_TOKEN не задан")
            break
        try:
            url = f"https://api.vk.com/method/wall.get?domain={group}&count=2&access_token={VK_TOKEN}&v=5.131"
            res = requests.get(url, timeout=10).json()

            if "error" in res:
                print(f"Ошибка VK API для {group}: {res['error'].get('error_msg')}")
                continue

            if "response" in res and "items" in res["response"]:
                posts = res["response"]["items"]
                for post in posts:
                    post_id = post["id"]

                    if group not in last_seen_ids:
                        last_seen_ids[group] = post_id
                        print(f"Запомнили начальный ID для {group}: {post_id}")
                        continue

                    if post_id > last_seen_ids[group]:
                        last_seen_ids[group] = post_id
                        raw_text = post.get("text", "")
                        post_url = f"https://vk.com/{group}?w=wall{post['owner_id']}_{post_id}"

                        main_text = f"🔔 <b>Новый пост в {group}!</b>\n\n{raw_text}\n\n🔗 <a href='{post_url}'>Источник в VK</a>"
                        photos, video_links = extract_attachments(post.get("attachments", []))

                        send_telegram_message(main_text, photos, video_links)
                        print(f"Отправка нового поста из {group} (ID {post_id})")
        except Exception as e:
            print(f"Ошибка при проверке группы {group}: {e}")

# ================= ФОНОВЫЕ ПОТОКИ =================
def worker_loop():
    print("Фоновый поток успешно запущен.")
    while True:
        try:
            check_vk_posts()
        except Exception as e:
            print(f"Ошибка во внутреннем цикле worker_loop: {e}")
        time.sleep(CHECK_INTERVAL)

def self_ping_loop():
    while True:
        time.sleep(600)
        try:
            requests.get(RENDER_URL, timeout=10)
            print("Self-ping отправлен успешно")
        except Exception as e:
            print(f"Ошибка Self-ping: {e}")

# ================= FLASK ВЕБ-ИНТЕРФЕЙС И API =================
@app.route('/', methods=['GET', 'HEAD'])
def index():
    if request.method == 'HEAD':
        return "", 200
    groups = get_groups()
    return render_template_string(HTML_TEMPLATE, groups=groups)

@app.route('/add', methods=['POST'])
def add_group():
    raw_group = request.form.get('group', '')
    group = clean_group_name(raw_group)

    if group:
        groups = get_groups()
        if group not in groups:
            groups.append(group)
            save_groups(groups)
    return f"<script>window.location.href='/';</script>"

@app.route('/delete', methods=['POST'])
def delete_group():
    raw_group = request.form.get('group', '')
    group = clean_group_name(raw_group)

    if group:
        groups = get_groups()
        if group in groups:
            groups.remove(group)
            save_groups(groups)
    return f"<script>window.location.href='/';</script>"

# ================= ТОЧКА ВХОДА =================
if __name__ == "__main__":
    print("=== ПРОВЕРКА КЛЮЧЕЙ ===")
    print(f"BIN_ID: {JSONBIN_BIN_ID}")
    print(f"API_KEY: {'Задан' if JSONBIN_API_KEY else 'НЕ ЗАДАН'}")

    threading.Thread(target=worker_loop, daemon=True).start()
    threading.Thread(target=self_ping_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
