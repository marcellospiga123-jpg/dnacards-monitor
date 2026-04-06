import requests
from bs4 import BeautifulSoup
import json
import datetime
import base64
import os
import time

# ======================
# CONFIG
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
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg
        }, timeout=10)
    except:
        print("Errore Telegram")

# ======================
# GITHUB
# ======================

def load_github():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            content = base64.b64decode(r.json()["content"]).decode()
            return json.loads(content), r.json()["sha"]
    except:
        pass

    return {}, None


def save_github(data, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    content = base64.b64encode(
        json.dumps(data, indent=2).encode()
    ).decode()

    payload = {
        "message": "update prezzi PRO",
        "content": content,
        "branch": "main"
    }

    if sha:
        payload["sha"] = sha

    try:
        requests.put(url, headers=headers, json=payload, timeout=10)
    except:
        print("Errore salvataggio")

# ======================
# SCRAPING PRO
# ======================

def scrape():
    prodotti = []

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for url in URLS:
        print("Scraping:", url)

        try:
            r = requests.get(url, headers=headers, timeout=15)
            html = r.text
        except:
            continue

        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".product")

        for item in items:
            try:
                nome = item.select_one("h2").text.strip()
                prezzo_raw = item.select_one(".price").text.strip()

                prezzo = float(
                    prezzo_raw.replace("€", "").replace(",", ".")
                )

                # ✅ DISPONIBILITÀ
                disponibile = True
                testo = item.text.lower()

                if "esaurito" in testo or "out of stock" in testo:
                    disponibile = False

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo,
                    "disponibile": disponibile
                })

            except:
                continue

        time.sleep(2)

    return prodotti

# ======================
# ANALISI PRO
# ======================

def analizza(storico, prodotto):
    nome = prodotto["nome"]
    prezzo = prodotto["prezzo"]

    if nome not in storico or len(storico[nome]) == 0:
        return None

    prezzi_passati = [x["prezzo"] for x in storico[nome]]

    minimo = min(prezzi_passati)
    ultimo = prezzi_passati[-1]

    variazione = prezzo - ultimo

    # ROI simulato
    roi = ((minimo - prezzo) / prezzo) * 100

    return {
        "min": minimo,
        "ultimo": ultimo,
        "variazione": variazione,
        "roi": round(roi, 2)
    }

# ======================
# MAIN
# ======================

def main():
    storico, sha = load_github()
    oggi = str(datetime.date.today())

    prodotti = scrape()

    if not prodotti:
        print("No prodotti")
        return

    for p in prodotti:
        nome = p["nome"]
        prezzo = p["prezzo"]
        disponibile = p["disponibile"]

        if nome not in storico:
            storico[nome] = []

        info = analizza(storico, p)

        # salva sempre
        storico[nome].append({
            "prezzo": prezzo,
            "data": oggi,
            "disponibile": disponibile
        })

        # ALERT PRO
        if info:
            if info["variazione"] < -5:  # calo forte
                msg = f"""🔥 CALO PREZZO

{nome}
💰 {info['ultimo']}€ → {prezzo}€
📉 {info['variazione']}€
💸 ROI: {info['roi']}%
📦 {'Disponibile' if disponibile else '❌ Esaurito'}
"""
                send_telegram(msg)

    save_github(storico, sha)

    print("FINE PRO")

# ======================
# RUN
# ======================

if __name__ == "__main__":
    main()
