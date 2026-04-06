import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

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
HISTORY_FILE = "price_history.json"
HEARTBEAT_FILE = "heartbeat.json"

# ===== LOAD =====
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
history = load_json(HISTORY_FILE)
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

def send_photo(chat_id, file_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    with open(file_path, "rb") as f:
        requests.post(url, data={"chat_id": chat_id, "caption": caption}, files={"photo": f})

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

# ===== PREZZO =====
def parse_price(price):
    try:
        return float(price.replace("€", "").replace(",", ".").split()[0])
    except:
        return 0

# ===== ROI =====
def calcola_roi(nome, prezzo):
    p = parse_price(prezzo)

    if "OP-05" in nome:
        resale = 140
    elif "OP-06" in nome:
        resale = 130
    elif "OP-07" in nome:
        resale = 125
    else:
        resale = 115

    if p == 0:
        return 0

    return round(((resale - p) / p) * 100, 2)

# ===== GRAFICO =====
def generate_graph(name):
    if name not in history or len(history[name]) < 2:
        return None

    prices = [x["price"] for x in history[name]]
    times = list(range(len(prices)))

    plt.figure()
    plt.plot(times, prices)
    plt.title(name[:40])
    plt.xlabel("Time")
    plt.ylabel("Price €")

    filename = f"graph_{hash(name)}.png"
    plt.savefig(filename)
    plt.close()

    return filename

# ===== TREND =====
def update_history(name, price):
    if name not in history:
        history[name] = []

    history[name].append({
        "price": price,
        "time": datetime.now().isoformat()
    })

    history[name] = history[name][-20:]

# ===== CLEAN =====
def clean_old_messages():
    now = datetime.now()
    return {
        k: v for k, v in messages.items()
        if now - datetime.fromisoformat(v) < timedelta(hours=24)
    }

# ===== HEARTBEAT =====
def send_heartbeat():
    now = datetime.now()
    last = heartbeat.get("last")

    if last:
        last = datetime.fromisoformat(last)
        if now - last < timedelta(hours=1):
            return

    send_telegram("🤖 Bot attivo (scalping + grafici)")
    heartbeat["last"] = now.isoformat()
    save_json(HEARTBEAT_FILE, heartbeat)

# ===== MAIN =====
def main():
    global storico, messages

    prodotti = get_products()
    messages = clean_old_messages()

    for p in prodotti:
        name = p["name"]
        price_val = parse_price(p["price_raw"])
        roi = calcola_roi(name, p["price_raw"])

        update_history(name, price_val)

        old = storico.get(name)

        is_new = old is None
        price_drop = old and price_val < parse_price(old["price_raw"])
        back_stock = old and not old["available"] and p["available"]

        if not (is_new or price_drop or back_stock):
            continue

        if name in messages:
            continue

        alert = ""
        if back_stock:
            alert = "🔥 TORNATO DISPONIBILE"
        elif price_drop:
            alert = "💸 PREZZO SCESO"
        elif roi > 25:
            alert = "💎 SUPER DEAL"

        stato = "✅ Disponibile" if p["available"] else "❌ Esaurito"

        text = f"""
{alert}

<b>{name}</b>

💰 {p['price_raw']}
{stato}
📈 ROI: {roi}%
"""

        send_telegram(text, p["link"])

        # GRAFICO
        graph = generate_graph(name)
        if graph:
            for chat_id in CHAT_IDS:
                send_photo(chat_id, graph, "📉 Andamento prezzo")

        messages[name] = datetime.now().isoformat()

    save_json(STORICO_FILE, {p["name"]: p for p in prodotti})
    save_json(MESSAGES_FILE, messages)
    save_json(HISTORY_FILE, history)

    send_heartbeat()

if __name__ == "__main__":
    main()
