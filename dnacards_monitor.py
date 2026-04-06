import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta

# ===== CONFIG =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_IDS = os.getenv("TELEGRAM_CHAT_ID").split(",")

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

STORICO_FILE = "storico.json"
MESSAGES_FILE = "messages.json"

# ===== LOAD FILES =====
def load_json(file):
    if not os.path.exists(file):
        return {}
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

storico = load_json(STORICO_FILE)
messages = load_json(MESSAGES_FILE)

# ===== TELEGRAM =====
def send_telegram(text, link):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    keyboard = {
        "inline_keyboard": [
            [{"text": "🛒 Compra ora", "url": link}]
        ]
    }

    for chat_id in CHAT_IDS:
        requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "reply_markup": keyboard,
            "parse_mode": "HTML"
        })

# ===== SCRAPER =====
def get_products():
    prodotti = []

    for url in URLS:
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "html.parser")

        cards = soup.select(".product")

        for c in cards:
            try:
                name = c.select_one(".woocommerce-loop-product__title").text.strip()
                price = c.select_one(".price").text.strip()
                link = c.select_one("a")["href"]

                disponibile = "Esaurito" not in c.text

                prodotti.append({
                    "name": name,
                    "price": price,
                    "link": link,
                    "available": disponibile
                })

            except:
                continue

    return prodotti

# ===== ROI (semplice simulazione) =====
def calcola_roi(prezzo):
    try:
        p = float(prezzo.replace("€", "").replace(",", "."))
        roi = round((120 - p) / p * 100, 2)
        return roi
    except:
        return 0

# ===== CLEAN 24H =====
def clean_old_messages():
    now = datetime.now()
    new_messages = {}

    for k, v in messages.items():
        t = datetime.fromisoformat(v)
        if now - t < timedelta(hours=24):
            new_messages[k] = v

    return new_messages

# ===== MAIN =====
def main():
    global storico, messages

    print("🔍 Controllo prodotti...")

    prodotti = get_products()
    print(f"PRODOTTI: {len(prodotti)}")

    messages = clean_old_messages()

    nuovi = 0

    for p in prodotti:
        key = p["name"]

        old = storico.get(key)

        cambiato = (
            old is None or
            old["price"] != p["price"] or
            old["available"] != p["available"]
        )

        if not cambiato:
            continue

        # evita spam
        if key in messages:
            continue

        stato = "✅ Disponibile" if p["available"] else "❌ Esaurito"
        roi = calcola_roi(p["price"])

        text = f"""
<b>{p['name']}</b>

💰 {p['price']}
{stato}
📈 ROI: {roi}%
"""

        send_telegram(text, p["link"])

        messages[key] = datetime.now().isoformat()
        nuovi += 1

    print(f"NUOVI ALERT: {nuovi}")

    # salva tutto
    save_json(STORICO_FILE, {p["name"]: p for p in prodotti})
    save_json(MESSAGES_FILE, messages)

    print("✅ Fine run")


# ===== START =====
if __name__ == "__main__":
    main()
