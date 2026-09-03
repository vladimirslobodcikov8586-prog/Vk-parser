import os
import time
import threading
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

# ================= НАСТРОЙКИ И ПЕРЕМЕННЫЕ =================
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
VK_TOKEN = os.getenv("VK_TOKEN")
JSONBIN_BIN_ID = os.getenv("JSONBIN_BIN_ID")
JSONBIN_API_KEY = os.getenv("JSONBIN_API_KEY")
RENDER_URL = os.getenv("RENDER_URL", "https://vk-parser-xhkd.onrender.com")

CHECK_INTERVAL = 300  # 5 минут (300 секунд)
STATUS_INTERVAL_CYCLES = 6  # Каждые 6 циклов (6 * 5 мин = 30 минут)

DEFAULT_GROUPS = ["kinopoisk", "vtorchermetekb", "barakholka_group_66"]
last_seen_ids = {}

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
    check_count = 0
    print("Фоновый поток успешно запущен.")

    while True:
        try:
            check_vk_posts()
            check_count += 1

            if check_count >= STATUS_INTERVAL_CYCLES:
                status_text = (
                    "🟢 <b>Бот работает штатно!</b>\n"
                    "Проверка пабликов проходит каждые 5 минут, новых постов пока нет."
                )
                send_telegram_message(status_text)
                print("Отправлено статусное сообщение (30 минут)")
                check_count = 0
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

# ================= FLASK API =================
@app.route('/', methods=['GET', 'HEAD'])
def index():
    return "VK Parser Bot is active!", 200

@app.route('/api/groups', methods=['GET'])
def api_get_groups():
    return jsonify({"groups": get_groups()}), 200

@app.route('/api/groups', methods=['POST'])
def api_add_group():
    data = request.get_json() or {}
    group = data.get("group", "").strip().lower()
    if "vk.com/" in group:
        group = group.split("vk.com/")[-1].strip("/")

    if not group:
        return jsonify({"error": "No group provided"}), 400

    groups = get_groups()
    if group not in groups:
        groups.append(group)
        if save_groups(groups):
            return jsonify({"status": "added", "groups": groups}), 200
        return jsonify({"error": "Failed to save"}), 500
    return jsonify({"status": "already exists", "groups": groups}), 200

# ================= ТОЧКА ВХОДА =================
if __name__ == "__main__":
    print("=== ПРОВЕРКА КЛЮЧЕЙ ===")
    print(f"BIN_ID: {JSONBIN_BIN_ID}")
    print(f"API_KEY: {'Задан' if JSONBIN_API_KEY else 'НЕ ЗАДАН'}")

    threading.Thread(target=worker_loop, daemon=True).start()
    threading.Thread(target=self_ping_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
