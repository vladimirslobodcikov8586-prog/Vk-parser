import os
import time
import requests

# Сервер сам подтянет ключи из настроек безопасным образом
VK_TOKEN = os.environ.get("VK_TOKEN")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

# Список групп VK (указывайте короткие имена после vk.com/)
GROUPS = [
    "durov",
    "ria",
    "kinopoisk"
]

# Проверка каждые 5 минут (300 секунд)
CHECK_INTERVAL = 300

last_seen_posts = {group: None for group in GROUPS}

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка TG: {e}")

def check_vk():
    print("Проверка обновлений в VK...")
    for group in GROUPS:
        url = "https://api.vk.com/method/wall.get"
        params = {
            "domain": group,
            "count": 2,
            "access_token": VK_TOKEN,
            "v": "5.131"
        }
        try:
            res = requests.get(url, params=params, timeout=10).json()
            if "response" in res and res["response"]["items"]:
                items = res["response"]["items"]
                post = items[0]
                if post.get("is_pinned") and len(items) > 1:
                    post = items[1]
                
                post_id = post["id"]
                owner_id = post["owner_id"]
                
                if last_seen_posts[group] is None:
                    last_seen_posts[group] = post_id
                    continue
                
                if post_id > last_seen_posts[group]:
                    last_seen_posts[group] = post_id
                    text = post.get("text", "Новый пост без текста (медиа)")
                    post_url = f"https://vk.com/wall{owner_id}_{post_id}"
                    
                    msg = (
                        f"🔔 <b>Новый пост в {group}!</b>\n\n"
                        f"{text[:600]}\n\n"
                        f"🔗 <a href='{post_url}'>Открыть в VK</a>"
                    )
                    send_telegram(msg)
        except Exception as e:
            print(f"Ошибка проверки {group}: {e}")

if __name__ == "__main__":
    send_telegram("🚀 <b>Серверный парсер VK успешно запущен на Render!</b>")
    while True:
        check_vk()
        time.sleep(CHECK_INTERVAL)
