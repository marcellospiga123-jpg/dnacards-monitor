import requests
from bs4 import BeautifulSoup
import json
import base64
import os
from datetime import datetime, timedelta

# ===== CONFIG =====
URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO = os.getenv("REPO")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

FILE_NAME = "storico.json"
HEART_FILE = "heartbeat.json"

# ===== TELEGRAM =====
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# ===== HEARTBEAT =====
def load_heartbeat():
    if os.path.exists(HEART_FILE):
        with open(HEART_FILE) as f:
            return json.load(f)
    return {"last": "2000-01-01T00:00:00"}

def save_heartbeat(data):
    with open(HEART_FILE, "w") as f:
        json.dump(data, f)

def heartbeat(prodotti):
    hb = load_heartbeat()
    last = datetime.fromisoformat(hb["last"])
    now = datetime.now()

    if now - last > timedelta(minutes=15):
        send_telegram(f"🤖 BOT ATTIVO\nProdotti: {len(prodotti)}")
        hb["last"] = now.isoformat()
        save_heartbeat(hb)

# ===== GITHUB LOAD =====
def load_from_github():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)

    print("LOAD GITHUB:", r.status_code)

    if r.status_code != 200:
        return {}, None

    data = r.json()
    content = base64.b64decode(data["content"]).decode()

    return json.loads(content), data["sha"]

# ===== GITHUB SAVE =====
def save_to_github(data, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}

    content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()

    payload = {
        "message": "update storico",
        "content": content
    }

    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)

    print("GITHUB STATUS:", r.status_code)

# ===== SCRAPER =====
def scrape():
    prodotti = []
    headers = {"User-Agent": "Mozilla/5.0"}

    for url in URLS:
        try:
            print("Scraping:", url)
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            for c in soup.select(".product"):
                nome = c.select_one("h2").text.strip()

                prezzo = 0
                prezzo_tag = c.select_one(".price")

                if prezzo_tag:
                    txt = prezzo_tag.text.replace("€", "").replace(",", ".")
                    try:
                        prezzo = float(txt.split()[0])
                    except:
                        prezzo = 0

                disponibile = True
                if "esaurito" in c.text.lower():
                    disponibile = False

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo,
                    "disponibile": disponibile
                })

        except Exception as e:
            print("Errore scraping:", e)

    print("PRODOTTI:", len(prodotti))
    return prodotti

# ===== CLEAN =====
def clean_old(data):
    now = datetime.now()

    for nome in list(data.keys()):
        data[nome] = [
            x for x in data[nome]
            if datetime.fromisoformat(x["time"]) > now - timedelta(hours=24)
        ]

        if not data[nome]:
            del data[nome]

    return data

# ===== MAIN =====
def main():
    storico, sha = load_from_github()

    if not isinstance(storico, dict):
        storico = {}

    prodotti = scrape()

    if not prodotti:
        send_telegram("❌ ERRORE SCRAPING")
        return

    heartbeat(prodotti)

    for p in prodotti:
        nome = p["nome"]

        if nome not in storico:
            storico[nome] = []

        last = storico[nome][-1] if storico[nome] else None

        # ===== ALERT =====
        if last:
            if p["prezzo"] != last["prezzo"]:
                send_telegram(f"💰 PREZZO CAMBIATO\n{nome}\n{last['prezzo']}€ → {p['prezzo']}€")

            if not last["disponibile"] and p["disponibile"]:
                send_telegram(f"🔥 DISPONIBILE\n{nome}")

        storico[nome].append({
            "prezzo": p["prezzo"],
            "disponibile": p["disponibile"],
            "time": datetime.now().isoformat()
        })

        # ===== ROI =====
        prezzi = [x["prezzo"] for x in storico[nome] if x["prezzo"] > 0]

        if len(prezzi) > 1:
            attuale = prezzi[-1]
            massimo = max(prezzi)
            minimo = min(prezzi)

            roi = ((massimo - attuale) / attuale * 100)

            if roi > 20:
                send_telegram(
                    f"🚀 ROI ALTO\n{nome}\n"
                    f"💰 {attuale}€\n"
                    f"📈 {massimo}€\n"
                    f"🔥 ROI {roi:.2f}%"
                )

    storico = clean_old(storico)
    save_to_github(storico, sha)

# ===== RUN =====
if __name__ == "__main__":
    main()
