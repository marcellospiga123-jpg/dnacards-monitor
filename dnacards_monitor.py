
import requests
from bs4 import BeautifulSoup
import os
import json
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STORICO_FILE = "storico.json"

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

# ---------- TELEGRAM ----------
def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg}
    )

# ---------- LOAD/SAVE ----------
def load_storico():
    if not os.path.exists(STORICO_FILE):
        return {}
    with open(STORICO_FILE, "r") as f:
        return json.load(f)

def save_storico(data):
    with open(STORICO_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ---------- CLEAN OLD ----------
def clean_old(storico):
    now = datetime.now()
    new_data = {}

    for k, v in storico.items():
        t = datetime.fromisoformat(v["time"])
        if now - t < timedelta(hours=24):
            new_data[k] = v

    return new_data

# ---------- SCRAPER ----------
def scrape():
    prodotti = []

    for url in URLS:
        res = requests.get(url)
        soup = BeautifulSoup(res.text, "html.parser")

        cards = soup.select(".product")

        for c in cards:
            nome = c.select_one("h2").text.strip()

            prezzo = 0
            p = c.select_one(".price")
            if p:
                prezzo = float(
                    p.text.replace("€", "").replace(",", ".").strip()
                )

            disponibile = "Esaurito" not in c.text

            prodotti.append({
                "nome": nome,
                "prezzo": prezzo,
                "disp": disponibile
            })

    return prodotti

# ---------- ROI ----------
def calcola_roi(prezzo):
    target = 120  # puoi cambiare
    return round(((target - prezzo) / prezzo) * 100, 2) if prezzo > 0 else 0

# ---------- MAIN ----------
def main():
    print("🚀 BOT AVVIATO")

    storico = load_storico()
    storico = clean_old(storico)

    prodotti = scrape()
    print(f"PRODOTTI: {len(prodotti)}")

    nuovi_alert = []

    for p in prodotti:
        key = p["nome"]
        prezzo = p["prezzo"]
        disp = p["disp"]

        old = storico.get(key)

        changed = False

        if not old:
            changed = True
        else:
            if old["prezzo"] != prezzo or old["disp"] != disp:
                changed = True

        if changed:
            roi = calcola_roi(prezzo)

            msg = f"📦 {key}\n💰 {prezzo}€\n"

            if disp:
                msg += "✅ Disponibile\n"
            else:
                msg += "❌ Esaurito\n"

            msg += f"📈 ROI: {roi}%"

            nuovi_alert.append(msg)

        storico[key] = {
            "prezzo": prezzo,
            "disp": disp,
            "time": datetime.now().isoformat()
        }

    save_storico(storico)

    # ---------- SEND ----------
    if nuovi_alert:
        send("🔥 NUOVI AGGIORNAMENTI 🔥")
        for m in nuovi_alert[:10]:
            send(m)

    send(f"💓 BOT ATTIVO\nProdotti: {len(prodotti)}")

if __name__ == "__main__":
    main()
