import requests
from bs4 import BeautifulSoup
import time
import os
import json
from datetime import datetime, timedelta

# ================= CONFIG =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_IDS = os.getenv("CHAT_IDS", "").split(",")

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

CHECK_INTERVAL = 300
FILE_STORICO = "storico.json"
FILE_MSG = "messaggi.json"

# ================= FILE =================
def load_json(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

storico = load_json(FILE_STORICO)
messaggi = load_json(FILE_MSG)

# ================= TELEGRAM =================
def send_telegram(msg, url=None):
    global messaggi

    for chat_id in CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "HTML"
        }

        if url:
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": [
                    [{"text": "🛒 Apri prodotto", "url": url}]
                ]
            })

        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=payload
        ).json()

        # salva ID messaggio
        if r.get("ok"):
            msg_id = r["result"]["message_id"]

            if chat_id not in messaggi:
                messaggi[chat_id] = []

            messaggi[chat_id].append({
                "id": msg_id,
                "time": datetime.now().isoformat()
            })

    save_json(FILE_MSG, messaggi)

# ================= CANCELLA MESSAGGI =================
def pulisci_messaggi():
    global messaggi

    now = datetime.now()

    for chat_id in list(messaggi.keys()):
        nuovi = []

        for m in messaggi[chat_id]:
            t = datetime.fromisoformat(m["time"])

            if now - t > timedelta(hours=24):
                # cancella messaggio
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage",
                    data={
                        "chat_id": chat_id,
                        "message_id": m["id"]
                    }
                )
            else:
                nuovi.append(m)

        messaggi[chat_id] = nuovi

    save_json(FILE_MSG, messaggi)

# ================= ROI =================
def calcola_roi(prezzo):
    valore_medio = 120
    return round(((valore_medio - prezzo) / prezzo) * 100, 2)

# ================= SCRAPER =================
def get_prodotti():
    prodotti = []

    for url in URLS:
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            items = soup.select(".product")

            for item in items:
                nome = item.select_one("h2").text.strip()
                prezzo = float(item.select_one(".price").text.replace("€", "").replace(",", "."))
                link = item.select_one("a")["href"]
                disponibile = "Esaurito" not in item.text

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo,
                    "link": link,
                    "disponibile": disponibile
                })

        except Exception as e:
            print("Errore scraping:", e)

    return prodotti

# ================= LOGICA =================
def check_prodotti():
    global storico

    prodotti = get_prodotti()

    print(f"PRODOTTI: {len(prodotti)}")

    for p in prodotti:
        key = p["nome"]

        old = storico.get(key, {})

        old_disp = old.get("disponibile")
        old_price = old.get("prezzo")

        roi = calcola_roi(p["prezzo"])

        msg = None

        if key not in storico:
            msg = f"🆕 <b>Nuovo prodotto</b>\n📦 {p['nome']}\n💰 {p['prezzo']}€\n📊 ROI: {roi}%"

        elif old_disp is False and p["disponibile"]:
            msg = f"🔥 <b>Tornato disponibile</b>\n📦 {p['nome']}\n💰 {p['prezzo']}€\n📊 ROI: {roi}%"

        elif old_price != p["prezzo"]:
            msg = f"💸 <b>Prezzo cambiato</b>\n📦 {p['nome']}\n💰 {old_price}€ ➜ {p['prezzo']}€\n📊 ROI: {roi}%"

        if msg:
            send_telegram(msg, p["link"])

        storico[key] = p

    save_json(FILE_STORICO, storico)

# ================= HEARTBEAT =================
def heartbeat():
    send_telegram(f"💓 Bot attivo {datetime.now().strftime('%H:%M:%S')}")

# ================= LOOP =================
def main():
    count = 0

    while True:
        try:
            check_prodotti()
            pulisci_messaggi()  # 🔥 CLEAN 24H

            count += 1
            if count % 6 == 0:
                heartbeat()

        except Exception as e:
            print("Errore:", e)

        time.sleep(CHECK_INTERVAL)

# ================= START =================
if __name__ == "__main__":
    main()
