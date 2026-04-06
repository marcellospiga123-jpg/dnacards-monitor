import requests
from bs4 import BeautifulSoup
import json
import os
import base64
from datetime import datetime, timedelta

# ===== CONFIG =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO = os.getenv("REPO")  # es: marcellospiga123-jpg/dnacards-monitor

FILE_NAME = "storico.json"

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

# ===== TELEGRAM =====
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram non configurato")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg
    })

# ===== SCRAPER =====
def scrape():
    prodotti = []

    for url in URLS:
        print("Scraping:", url)
        r = requests.get(url, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        cards = soup.select(".product")

        for c in cards:
            nome = c.select_one(".woocommerce-loop-product__title")
            prezzo = c.select_one(".price")
            text = c.text.lower()

            if not nome or not prezzo:
                continue

            disponibile = "esaurito" not in text

            try:
                prezzo_val = float(prezzo.text.replace("€", "").replace(",", ".").strip())
            except:
                continue

            prodotti.append({
                "nome": nome.text.strip(),
                "prezzo": prezzo_val,
                "disponibile": disponibile
            })

    print("PRODOTTI:", len(prodotti))
    return prodotti

# ===== GITHUB =====
def get_github_file():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)

    print("GITHUB STATUS:", r.status_code)

    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"]).decode()
        return json.loads(content), r.json()["sha"]
    else:
        return [], None

def save_to_github(storico, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    content = base64.b64encode(json.dumps(storico, indent=2).encode()).decode()

    payload = {
        "message": "update dati",
        "content": content
    }

    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)

    print("UPLOAD STATUS:", r.status_code)
    print(r.text)

# ===== ROI =====
def calcola_roi(prodotti):
    prezzi = [p["prezzo"] for p in prodotti if p["disponibile"]]
    if len(prezzi) < 2:
        return 0
    return round((max(prezzi) - min(prezzi)) / min(prezzi) * 100, 2)

# ===== PULIZIA 24H =====
def pulisci_storico(storico):
    nuovo = []
    limite = datetime.now() - timedelta(hours=24)

    for entry in storico:
        ts = datetime.fromisoformat(entry["timestamp"])
        if ts > limite:
            nuovo.append(entry)

    return nuovo

# ===== CONFRONTO =====
def confronta(vecchi, nuovi):
    notifiche = []

    if not vecchi:
        return []

    ultimi = vecchi[-1]["prodotti"]

    for p in nuovi:
        for old in ultimi:
            if p["nome"] == old["nome"]:
                # prezzo cambiato
                if p["prezzo"] != old["prezzo"]:
                    notifiche.append(f"💰 Prezzo cambiato:\n{p['nome']}\n{old['prezzo']}€ → {p['prezzo']}€")

                # torna disponibile
                if p["disponibile"] and not old["disponibile"]:
                    notifiche.append(f"🔥 Disponibile di nuovo:\n{p['nome']}")

    return notifiche

# ===== HEARTBEAT =====
def heartbeat():
    send_telegram("💓 Bot attivo (heartbeat 15 min)")

# ===== MAIN =====
def main():
    prodotti = scrape()

    if not prodotti:
        send_telegram("❌ Nessun prodotto trovato")
        return

    storico, sha = get_github_file()

    storico = pulisci_storico(storico)

    notifiche = confronta(storico, prodotti)

    # aggiungi nuovi dati
    storico.append({
        "timestamp": datetime.now().isoformat(),
        "prodotti": prodotti
    })

    save_to_github(storico, sha)

    disponibili = [p for p in prodotti if p["disponibile"]]

    msg = f"""🤖 BOT ATTIVO
Prodotti: {len(prodotti)}
Disponibili: {len(disponibili)}
ROI: {calcola_roi(prodotti)}%
"""

    send_telegram(msg)

    for n in notifiche:
        send_telegram(n)

# ===== RUN =====
if __name__ == "__main__":
    main()
