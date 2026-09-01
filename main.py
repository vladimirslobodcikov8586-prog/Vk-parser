import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# 1. Мини-веб-сервер для Render с поддержкой GET и HEAD
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def respond_ok(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()

    def do_GET(self):
        self.respond_ok()
        self.wfile.write('Бот VK Parser успешно работает 24/7!'.encode('utf-8'))

    def do_HEAD(self):
        self.respond_ok()

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"Веб-сервер запущен на порту {port}", flush=True)
    server.serve_forever()

# Запускаем веб-сервер в отдельном потоке
threading.Thread(target=run_web_server, daemon=True).start()

# 2. Основной код парсера VK
VK_TOKEN = os.environ.get("VK_TOKEN")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

GROUPS = ["durov", "ria", "kinopoisk"]  # Короткие имена групп VK
CHECK_INTERVAL = 300  # Проверка каждые 5 минут

def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("Ошибка: TG_TOKEN или TG_CHAT_ID не заданы в Environment!", flush=True)
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload)
        print(f"Ответ Telegram API: {res.status_code} - {res.text}", flush=True)
    except Exception as e:
        print(f"Ошибка отправки в TG: {e}", flush=True)

# Сообщение о старте
send_telegram("🚀 Парсер VK успешно запущен и работает на Render!")

last_seen_ids = {}

while True:
    try:
        for group in GROUPS:
            if not VK_TOKEN:
                print("Ошибка: VK_TOKEN не задан в Environment!", flush=True)
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
