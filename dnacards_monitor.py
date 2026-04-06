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
HEARTBEAT_FILE = "heartbeat.json"

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
    "Connection": "keep-alive"
}

# ======================
# TELEGRAM
# ======================

def send_telegram(msg, log):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        ).json()

        print("TELEGRAM:", r)

        if "result" in r:
            log.append({
                "id": r["result"]["message_id"],
                "time": time.time()
            })
    except Exception as e:
        print("Errore Telegram:", e)

def delete_old_messages(log):
    now = time.time()
    nuovi = []

    for m in log:
        if now - m["time"] > 86400:
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
# HEARTBEAT
# ======================

def load_heartbeat():
    if os.path.exists(HEARTBEAT_FILE):
        with open(HEARTBEAT_FILE) as f:
            return json.load(f)
    return {"last": 0}

def save_heartbeat(data):
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump(data, f)

def heartbeat(log, prodotti):
    hb = load_heartbeat()
    now = time.time()

    if now - hb["last"] > 900:
        send_telegram(f"🤖 BOT ATTIVO\nProdotti trovati: {len(prodotti)}", log)
        hb["last"] = now
        save_heartbeat(hb)

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
    try:
        url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}

        r = requests.get(url, headers=headers, timeout=10)

        print("LOAD GITHUB STATUS:", r.status_code)

        if r.status_code == 200:
            content = base64.b64decode(r.json()["content"]).decode()
            return json.loads(content), r.json()["sha"]

    except Exception as e:
        print("Errore load GitHub:", e)

    return {}, None

def save_github(data, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    content = base64.b64encode(
        json.dumps(data, indent=2).encode()
    ).decode()

    payload = {
        "message": "update prezzi automatico",
        "content": content,
        "branch": "main"
    }

    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)

    print("GITHUB STATUS:", r.status_code)
    print("GITHUB RESPONSE:", r.text)

# ======================
# SCRAPING
# ======================

def fetch_with_retry(url):
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            print("Retry errore:", e)
            time.sleep(5)
    return None

def scrape():
    prodotti = []

    for url in URLS:
        print("Scraping:", url)

        html = fetch_with_retry(url)

        if not html:
            print("❌ HTML non ricevuto")
            continue

        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("li.product")

        print("Trovati:", len(items))

        if len(items) == 0:
            print("⚠️ BLOCCO o HTML cambiato")
            continue

        for item in items:
            try:
                nome = item.select_one("h2").text.strip()

                prezzo_raw = item.select_one(".price").text
                prezzo = float(
                    prezzo_raw.replace("€", "")
                    .replace(",", ".")
                    .strip()
                )

                disponibile = True
                if "esaurito" in item.text.lower():
                    disponibile = False

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo,
                    "disponibile": disponibile
                })

            except Exception as e:
                print("Errore parsing:", e)

        time.sleep(3)

    print("PRODOTTI TOTALI:", len(prodotti))
    return prodotti

# ======================
# MAIN
# ======================

def main():
    storico, sha = load_github()
    log = load_local(MSG_FILE)

    oggi = str(datetime.date.today())

    prodotti = scrape()

    print("DEBUG PRODOTTI:", prodotti)

    if not prodotti:
        print("⚠️ NESSUN PRODOTTO")
        return

    heartbeat(log, prodotti)

    for p in prodotti:
        nome = p["nome"]
        prezzo = p["prezzo"]
        disponibile = p["disponibile"]

        storico.setdefault(nome, [])

        storico[nome].append({
            "prezzo": prezzo,
            "data": oggi,
            "disponibile": disponibile
        })

    log = delete_old_messages(log)
    save_local(MSG_FILE, log)

    save_github(storico, sha)

if __name__ == "__main__":
    main()
