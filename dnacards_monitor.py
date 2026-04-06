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
MSG_FILE = "messages.json"

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

# ======================
# TELEGRAM
# ======================

def send_telegram(msg, log):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        ).json()

        log.append({
            "id": r["result"]["message_id"],
            "time": time.time()
        })

    except:
        print("Errore Telegram")

def delete_old_messages(log):
    now = time.time()
    nuovi = []

    for m in log:
        if now - m["time"] > 86400:  # 24h
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage",
                    data={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "message_id": m["id"]
                    }
                )
            except:
                continue
        else:
            nuovi.append(m)

    return nuovi

# ======================
# FILE LOCALI
# ======================

def load_local(file):
    if os.path.exists(file):
        with open(file) as f:
            return json.load(f)
    return []

def save_local(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

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
# SCRAPING
# ======================

def scrape():
    prodotti = []

    headers = {"User-Agent": "Mozilla/5.0"}

    for url in URLS:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            for item in soup.select(".product"):
                try:
                    nome = item.select_one("h2").text.strip()
                    prezzo = float(item.select_one(".price").text.strip().replace("€","").replace(",","."))

                    disponibile = True
                    if "esaurito" in item.text.lower():
                        disponibile = False

                    prodotti.append({
                        "nome": nome,
                        "prezzo": prezzo,
                        "disponibile": disponibile
                    })
                except:
                    continue

        except:
            continue

        time.sleep(2)

    return prodotti

# ======================
# ANALISI
# ======================

def analizza(storico, nome, prezzo):
    if nome not in storico or len(storico[nome]) < 2:
        return None

    prezzi = [x["prezzo"] for x in storico[nome]]
    ultimo = prezzi[-1]
    minimo = min(prezzi)

    variazione = prezzo - ultimo
    roi = ((minimo - prezzo) / prezzo) * 100

    return variazione, round(roi, 2), ultimo

# ======================
# MAIN
# ======================

def main():
    storico, sha = load_github()
    log = load_local(MSG_FILE)

    oggi = str(datetime.date.today())
    prodotti = scrape()

    # HEARTBEAT
    send_telegram(f"🤖 BOT ATTIVO\n📦 Prodotti: {len(prodotti)}", log)

    for p in prodotti:
        nome = p["nome"]
        prezzo = p["prezzo"]
        disponibile = p["disponibile"]

        storico.setdefault(nome, [])

        res = analizza(storico, nome, prezzo)

        storico[nome].append({
            "prezzo": prezzo,
            "data": oggi,
            "disponibile": disponibile
        })

        if res:
            variazione, roi, ultimo = res

            if variazione < -5:
                send_telegram(
                    f"🔥 CALO\n{nome}\n{ultimo}€ → {prezzo}€\nROI {roi}%",
                    log
                )

        if not disponibile:
            send_telegram(f"❌ ESAURITO:\n{nome}", log)

    # PULIZIA 24H
    log = delete_old_messages(log)
    save_local(MSG_FILE, log)

    save_github(storico, sha)

if __name__ == "__main__":
    main()
