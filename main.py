import os
import time
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

os.environ["PYTHONUNBUFFERED"] = "1"

JSONBIN_BIN_ID = os.environ.get("JSONBIN_BIN_ID")
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY")

DEFAULT_GROUPS = ["durov", "ria", "kinopoisk"]

def load_groups():
    print("=== ПРОВЕРКА КЛЮЧЕЙ ===")
    print("BIN_ID:", JSONBIN_BIN_ID)
    print("API_KEY:", "Задан" if JSONBIN_API_KEY else "ОТСУТСТВУЕТ")
    
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
        print("⚠️ Ключи JSONBin не найдены. Загружаем дефолт.")
        return list(DEFAULT_GROUPS)
    
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
    headers = {"X-Master-Key": JSONBIN_API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=7)
        print(f"Запрос к JSONBin при запуске. Статус: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            record = data.get("record")
            if isinstance(record, list):
                print("Загружен список групп:", record)
                return record
            elif isinstance(record, dict) and "groups" in record:
                print("Загружен список групп (dict):", record["groups"])
                return record["groups"]
    except Exception as e:
        print("Ошибка загрузки групп:", e)
        
    return list(DEFAULT_GROUPS)

def save_groups(groups):
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
        return
    
    url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
    headers = {
        "Content-Type": "application/json",
        "X-Master-Key": JSONBIN_API_KEY
    }
    try:
        res = requests.put(url, headers=headers, json=groups, timeout=7)
        print(f"Результат сохранения в JSONBin: HTTP {res.status_code}")
    except Exception as e:
        print("Ошибка сохранения групп:", e)

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
            self.wfile.write('Бот VK Parser работает!'.encode('utf-8'))

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

def keep_alive():
    """Самопинг каждые 10 минут, чтобы Render не усыплял сервис"""
    my_url = "https://vk-parser-xhkd.onrender.com"
    while True:
        time.sleep(600)  # каждые 10 минут
        try:
            requests.get(my_url, timeout=10)
            print("Self-ping отправлен успешно")
        except Exception as e:
            print("Ошибка self-ping:", e)

threading.Thread(target=run_web_server, daemon=True).start()
threading.Thread(target=keep_alive, daemon=True).start()

VK_TOKEN = os.environ.get("VK_TOKEN")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
CHECK_INTERVAL = 300  # Проверка VK каждые 5 минут

def send_telegram_post(text, photos, video_links):
    if not TG_TOKEN or not TG_CHAT_ID:
        return

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
        print("Ошибка отправки в Telegram:", e)

def extract_attachments(attachments_data):
    photos = []
    video_links = []
    
    for att in attachments_data:
        att_type = att.get("type")
        
        if att_type == "photo":
            sizes = att["photo"].get("sizes", [])
            if sizes:
                best_size = max(sizes, key=lambda s: s.get("width", 0) * s.get("height", 0))
                photos.append(best_size["url"])
                
        elif att_type == "video":
            video_info = att["video"]
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

last_seen_ids = {}

while True:
    try:
        current_groups = list(GROUPS)
        print(f"Проверка постов для групп: {current_groups}")
        for group in current_groups:
            if not VK_TOKEN:
                print("⚠️ Переменная VK_TOKEN не задана!")
                break
                
            url = f"https://api.vk.com/method/wall.get?domain={group}&count=2&access_token={VK_TOKEN}&v=5.131"
            res = requests.get(url, timeout=10).json()
            
            if "error" in res:
                print(f"Ошибка VK API для {group}: {res['error'].get('error_msg')}")
                continue

            if "response" in res and "items" in res["response"]:
                posts = res["response"]["items"]
                for post in posts:
                    post_id = post["id"]
                    
                    # При первом старте запоминаем последний ID постов без рассылки
                    if group not in last_seen_ids:
                        last_seen_ids[group] = post_id
                        print(f"Запомнили начальный ID для {group}: {post_id}")
                        continue
                    
                    # Если появился действительно новый пост
                    if post_id > last_seen_ids[group]:
                        last_seen_ids[group] = post_id
                        
                        raw_text = post.get("text", "")
                        post_url = f"https://vk.com/{group}?w=wall{post['owner_id']}_{post_id}"
                        
                        main_text = f"🔔 <b>Новый пост в {group}!</b>\n\n{raw_text}\n\n🔗 <a href='{post_url}'>Источник в VK</a>"
                        
                        attachments = post.get("attachments", [])
                        photos, video_links = extract_attachments(attachments)
                        
                        print(f"Отправка нового поста из {group} (ID {post_id})")
                        send_telegram_post(main_text, photos, video_links)
    except Exception as e:
        print("Ошибка в цикле парсера:", e)
        
    time.sleep(CHECK_INTERVAL)
