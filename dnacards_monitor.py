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
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10
        ).json()

        if "result" in r:
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
# HEARTBEAT 15 MIN
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
        msg = f"""🤖 BOT ATTIVO

📦 Prodotti: {len(prodotti)}
⏱️ Check ogni 15 min
✅ Sistema operativo
"""
        send_telegram(msg, log)

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
    if not GITHUB_TOKEN or not REPO:
        return {}, None

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
    if not GITHUB_TOKEN or not REPO:
        return

    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    content = base64.b64encode(
        json.dumps(data, indent=2).encode()
    ).decode()

    payload = {
        "message": "update prezzi AUTO",
        "content": content,
        "branch": "main"
    }

    if sha:
        payload["sha"] = sha

    try:
        requests.put(url, headers=headers, json=payload, timeout=10)
    except:
        print("Errore salvataggio GitHub")

# ======================
# SCRAPING (FIXED)
# ======================

def scrape():
    prodotti = []

    for url in URLS:
        print("Scraping:", url)

        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            soup = BeautifulSoup(r.text, "html.parser")

            items = soup.select("li.product")

            print("Trovati:", len(items))

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

                except:
                    continue

        except Exception as e:
            print("Errore scraping:", e)

        time.sleep(2)

    print("PRODOTTI TOTALI:", len(prodotti))
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

    if not prodotti:
        print("⚠️ Nessun prodotto trovato")
        return

    heartbeat(log, prodotti)

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

    log = delete_old_messages(log)
    save_local(MSG_FILE, log)

    save_github(storico, sha)

if __name__ == "__main__":
    main()
