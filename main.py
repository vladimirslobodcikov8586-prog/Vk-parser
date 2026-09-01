
import os
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# Загружаем ключи из переменных окружения Render
JSONBIN_BIN_ID = os.environ.get("JSONBIN_BIN_ID")
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY")

DEFAULT_GROUPS = ["durov", "ria", "kinopoisk"]

def load_groups():
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
        return DEFAULT_GROUPS
    
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
    headers = {"X-Master-Key": JSONBIN_API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json().get("record", DEFAULT_GROUPS)
    except Exception as e:
        print("Ошибка загрузки из JSONBin:", e)
    return DEFAULT_GROUPS

def save_groups(groups):
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
        return
    
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
    headers = {
        "Content-Type": "application/json",
        "X-Master-Key": JSONBIN_API_KEY
    }
    try:
        requests.put(url, headers=headers, json=groups, timeout=5)
    except Exception as e:
        print("Ошибка сохранения в JSONBin:", e)

GROUPS = load_groups()

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
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
                
                if "vk.com/" in new_group:
                    new_group = new_group.split("vk.com/")[-1].strip("/")

                if new_group and new_group not in GROUPS:
                    GROUPS.append(new_group)
                    save_groups(GROUPS)
                    self._set_headers(200)
                    self.wfile.write(json.dumps({"status": "ok", "groups": GROUPS}).encode('utf-8'))
                else:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"status": "exists_or_empty"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def do_DELETE(self):
        global GROUPS
        if self.path == "/api/groups":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                target_group = data.get("group", "").strip().lower()
                
                if target_group in GROUPS:
                    GROUPS.remove(target_group)
                    save_groups(GROUPS)
                    self._set_headers(200)
                    self.wfile.write(json.dumps({"status": "deleted", "groups": GROUPS}).encode('utf-8'))
                else:
                    self._set_headers(404)
                    self.wfile.write(json.dumps({"status": "not_found"}).encode('utf-8'))
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

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
        pass

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
    except Exception:
        pass
        
    time.sleep(CHECK_INTERVAL)
