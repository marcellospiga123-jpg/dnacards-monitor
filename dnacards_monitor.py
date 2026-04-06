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
HEARTBEAT_FILE = "heartbeat.json"

# ===== UTIL =====
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
heartbeat = load_json(HEARTBEAT_FILE)

# ===== TELEGRAM =====
def send_telegram(text, link=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": None,
        "text": text,
        "parse_mode": "HTML"
    }

    if link:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": "🛒 Compra ora", "url": link}]
            ]
        }

    for chat_id in CHAT_IDS:
        payload["chat_id"] = chat_id
        requests.post(url, json=payload)

# ===== SCRAPER =====
def get_products():
    prodotti = []

    for url in URLS:
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            cards = soup.select(".product")

            for c in cards:
                try:
                    name = c.select_one(".woocommerce-loop-product__title").text.strip()
                    price_raw = c.select_one(".price").text.strip()
                    link = c.select_one("a")["href"]

                    disponibile = "Esaurito" not in c.text

                    prodotti.append({
                        "name": name,
                        "price_raw": price_raw,
                        "link": link,
                        "available": disponibile
                    })

                except:
                    continue

        except:
            continue

    return prodotti

# ===== PARSE PREZZO =====
def parse_price(price):
    try:
        return float(price.replace("€", "").replace(",", ".").split()[0])
    except:
        return 0

# ===== ROI REALE =====
def calcola_roi(nome, prezzo):
    p = parse_price(prezzo)

    # stima valore medio rivendita (logica migliorata)
    if "OP-05" in nome or "OP05" in nome:
        resale = 140
    elif "OP-06" in nome:
        resale = 130
    elif "OP-07" in nome:
        resale = 125
    elif "PRB" in nome:
        resale = 110
    else:
        resale = 115

    if p == 0:
        return 0

    roi = ((resale - p) / p) * 100
    return round(roi, 2)

# ===== CLEAN 24H =====
def clean_old_messages():
    now = datetime.now()
    new = {}

    for k, v in messages.items():
        t = datetime.fromisoformat(v)
        if now - t < timedelta(hours=24):
            new[k] = v

    return new

# ===== HEARTBEAT =====
def send_heartbeat():
    now = datetime.now()

    last = heartbeat.get("last")
    if last:
        last = datetime.fromisoformat(last)
        if now - last < timedelta(hours=1):
            return

    send_telegram("🤖 Bot attivo e funzionante")
    heartbeat["last"] = now.isoformat()
    save_json(HEARTBEAT_FILE, heartbeat)

# ===== MAIN =====
def main():
    global storico, messages

    print("🔍 Scan prodotti...")

    prodotti = get_products()
    print(f"Prodotti trovati: {len(prodotti)}")

    messages = clean_old_messages()

    nuovi = 0

    for p in prodotti:
        key = p["name"]

        old = storico.get(key)

        prezzo = parse_price(p["price_raw"])
        roi = calcola_roi(p["name"], p["price_raw"])

        cambiato = (
            old is None or
            old["price_raw"] != p["price_raw"] or
            old["available"] != p["available"]
        )

        if not cambiato:
            continue

        # anti spam
        if key in messages:
            continue

        # filtro intelligente (evita roba inutile)
        if roi < 5:
            continue

        stato = "✅ Disponibile" if p["available"] else "❌ Esaurito"

        text = f"""
<b>{p['name']}</b>

💰 {p['price_raw']}
{stato}
📈 ROI: {roi}%
"""

        send_telegram(text, p["link"])

        messages[key] = datetime.now().isoformat()
        nuovi += 1

    print(f"Nuovi alert: {nuovi}")

    # heartbeat
    send_heartbeat()

    # salva
    save_json(STORICO_FILE, {p["name"]: p for p in prodotti})
    save_json(MESSAGES_FILE, messages)

    print("✅ Fine")

# ===== START =====
if __name__ == "__main__":
    main()
