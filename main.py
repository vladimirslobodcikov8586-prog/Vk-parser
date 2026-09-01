
import os
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

GROUPS_FILE = "groups.json"

# Загрузка и сохранение списка групп
def load_groups():
    if os.path.exists(GROUPS_FILE):
        try:
            with open(GROUPS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return ["durov", "ria", "kinopoisk"]

def save_groups(groups):
    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)

GROUPS = load_groups()

# Веб-сервер с обработкой добавления групп из VK Feed Pulse
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        # Разрешаем CORS-запросы из браузера
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_GET(self):
        if self.path == "/api/groups":
            self._set_headers(200)
            self.wfile.write(json.dumps({"groups": GROUPS}).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write('Бот VK Parser и VK Feed Pulse работают 24/7!'.encode('utf-8'))

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        global GROUPS
        if self.path == "/api/groups":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                new_group = data.get("group", "").strip().lower()
                
                # Очищаем от ссылок, если вставили полное URL
                if "vk.com/" in new_group:
                    new_group = new_group.split("vk.com/")[-1].strip("/")

                if new_group and new_group not in GROUPS:
                    GROUPS.append(new_group)
                    save_groups(GROUPS)
                    print(f"Добавлена новая группа: {new_group}", flush=True)
                    self._set_headers(200)
                    self.wfile.write(json.dumps({"status": "ok", "groups": GROUPS}).encode('utf-8'))
                else:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"status": "exists_or_empty"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"Сервер запущен на порту {port}", flush=True)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# Переменные окружения
VK_TOKEN = os.environ.get("VK_TOKEN")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
CHECK_INTERVAL = 300

def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Ошибка отправки в TG: {e}", flush=True)

send_telegram("🚀 Сервер обновлён! Поддержка VK Feed Pulse подключена.")

last_seen_ids = {}

while True:
    try:
        current_groups = list(GROUPS)
        for group in current_groups:
            if not VK_TOKEN:
                break
                
            url = f"https://api.vk.com/method/wall.get?domain={group}&count=2&access_token={VK_TOKEN}&v=5.131"
            res = requests.get(url).json()
            
            if "response" in res and "items" in res["response"]:
                posts = res["response"]["items"]
                for post in posts:
                    post_id = post["id"]
                    if group not in last_seen_ids:
                        last_seen_ids[group] = post_id
                        continue
                    
                    if post_id > last_seen_ids[group]:
                        last_seen_ids[group] = post_id
                        text = post.get("text", "")
                        post_url = f"https://vk.com/{group}?w=wall{post['owner_id']}_{post_id}"
                        msg = f"🔔 <b>Новый пост в {group}!</b>\n\n{text[:500]}...\n\n🔗 <a href='{post_url}'>Читать в VK</a>"
                        send_telegram(msg)
    except Exception as e:
        print(f"Ошибка при парсинге: {e}", flush=True)
        
    time.sleep(CHECK_INTERVAL)
