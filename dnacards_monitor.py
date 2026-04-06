import requests
from bs4 import BeautifulSoup
import json
import datetime
import base64
import os

# ======================
# CONFIG (DA GITHUB SECRETS)
# ======================

GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO = os.getenv("REPO")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

FILE_NAME = "storico.json"

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

# ======================
# TELEGRAM
# ======================

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram non configurato")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg
    }
    requests.post(url, data=data)

# ======================
# GITHUB LOAD
# ======================

def load_github():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}"
    }

    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"]).decode()
        return json.loads(content), r.json()["sha"]

    return {}, None

# ======================
# GITHUB SAVE
# ======================

def save_github(data, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}"
    }

    content = base64.b64encode(
        json.dumps(data, indent=2).encode()
    ).decode()

    payload = {
        "message": "update storico prezzi",
        "content": content,
        "branch": "main"
    }

    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)

    print("SAVE STATUS:", r.status_code)
    print(r.text)

# ======================
# SCRAPING DNA
# ======================

def scrape():
    prodotti = []

    for url in URLS:
        print("Scraping:", url)

        html = requests.get(url).text
        soup = BeautifulSoup(html, "html.parser")

        items = soup.select(".product")

        for item in items:
            try:
                nome = item.select_one("h2").text.strip()
                prezzo = item.select_one(".price").text.strip()

                prezzo = prezzo.replace("€", "").replace(",", ".")
                prezzo = float(prezzo)

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo
                })

            except:
                continue

    return prodotti

# ======================
# MAIN
# ======================

def main():
    print("START BOT")

    storico, sha = load_github()

    oggi = str(datetime.date.today())

    prodotti = scrape()

    if not prodotti:
        print("Nessun prodotto trovato")
        return

    messaggi = []

    for p in prodotti:
        nome = p["nome"]
        prezzo = p["prezzo"]

        if nome not in storico:
            storico[nome] = []

        storico[nome].append({
            "prezzo": prezzo,
            "data": oggi
        })

        # ALERT: se prezzo basso
        if prezzo < 80:
            messaggi.append(f"🔥 OFFERTA:\n{nome}\n💰 {prezzo}€")

    save_github(storico, sha)

    # TELEGRAM
    for m in messaggi:
        send_telegram(m)

    print("FINE")

# ======================
# RUN
# ======================

if __name__ == "__main__":
    main()
