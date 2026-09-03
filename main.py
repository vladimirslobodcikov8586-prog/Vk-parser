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
BIN_ID = os.getenv("BIN_ID")
API_KEY = os.getenv("API_KEY")
RENDER_URL = os.getenv("RENDER_URL", "https://vk-parser-xhkd.onrender.com")

CHECK_INTERVAL = 300  # 5 минут (300 секунд)
STATUS_INTERVAL_CYCLES = 6  # Каждые 6 циклов (6 * 5 мин = 30 минут)

JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
JSONBIN_HEADERS = {
    "X-Master-Key": API_KEY,
    "Content-Type": "application/json"
}

last_seen_ids = {}

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================
def send_telegram_message(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("Ошибка: TG_TOKEN или TG_CHAT_ID не заданы")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

def get_groups():
    try:
        res = requests.get(JSONBIN_URL, headers=JSONBIN_HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data.get("record", {}).get("groups", [])
        print(f"Ошибка JSONBin: Status {res.status_code}")
        return []
    except Exception as e:
        print(f"Ошибка загрузки групп из JSONBin: {e}")
        return []

def save_groups(groups_list):
    try:
        payload = {"groups": groups_list}
        res = requests.put(JSONBIN_URL, headers=JSONBIN_HEADERS, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Ошибка сохранения групп в JSONBin: {e}")
        return False

def check_vk_posts():
    groups = get_groups()
    if not groups:
        print("Список групп пуст или не удалось загрузить.")
        return

    print(f"Проверка постов для групп: {groups}")
    for group in groups:
        try:
            url = f"https://api.vk.com/method/wall.get?domain={group}&count=2&access_token={VK_TOKEN}&v=5.131"
            res = requests.get(url, timeout=10).json()
            
            if "response" in res and "items" in res["response"]:
                items = res["response"]["items"]
                if not items:
                    continue

                latest_post = items[0]
                post_id = latest_post["id"]

                # Если группу проверяем впервые — запоминаем текущий ID и не спамим
                if group not in last_seen_ids:
                    last_seen_ids[group] = post_id
                    print(f"Запомнили начальный ID для {group}: {post_id}")
                    continue

                # Если появилось новое сообщение
                if post_id > last_seen_ids[group]:
                    last_seen_ids[group] = post_id
                    text = latest_post.get("text", "")
                    post_url = f"https://vk.com/{group}?w=wall{latest_post['owner_id']}_{post_id}"
                    
                    msg = f"🔔 **Новый пост в {group}!**\n\n{text[:500]}\n\n🔗 [Читать полностью]({post_url})"
                    send_telegram_message(msg)
                    print(f"Отправка нового поста из {group} (ID {post_id})")

        except Exception as e:
            print(f"Ошибка при проверке группы {group}: {e}")

# ================= ФОНОВЫЙ ПОТОК =================
def worker_loop():
    check_count = 0
    print("Фоновый поток успешно запущен.")
    
    while True:
        try:
            check_vk_posts()
            check_count += 1
            
            # Отправка статусного сообщения каждые 30 минут (6 циклов по 5 минут)
            if check_count >= STATUS_INTERVAL_CYCLES:
                status_text = (
                    "🟢 **Бот работает штатно!**\n"
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
        time.sleep(600)  # каждые 10 минут
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
    return jsonify(get_groups()), 200

@app.route('/api/groups', methods=['POST'])
def api_add_group():
    data = request.get_json()
    group = data.get("group")
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
    print(f"BIN_ID: {BIN_ID}")
    print(f"API_KEY: {'Задан' if API_KEY else 'НЕ ЗАДАН'}")

    # Запуск фоновых потоков
    t_worker = threading.Thread(target=worker_loop, daemon=True)
    t_worker.start()

    t_ping = threading.Thread(target=self_ping_loop, daemon=True)
    t_ping.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
