import requests
from bs4 import BeautifulSoup
import os
import json
import base64
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
REPO = os.getenv("REPO")
GH_TOKEN = os.getenv("GH_TOKEN")

STORICO_FILE = "storico.json"
UTENTI_FILE = "utenti.json"

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

# ---------- TELEGRAM ----------
def send(chat_id, msg):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": chat_id, "text": msg}
    )

def broadcast(msg, utenti):
    for u in utenti:
        send(u, msg)

# ---------- GITHUB ----------
def get_file(name):
    url = f"https://api.github.com/repos/{REPO}/contents/{name}"
    headers = {"Authorization": f"token {GH_TOKEN}"}
    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"]).decode()
        return json.loads(content), r.json()["sha"]
    return {}, None

def save_file(name, data, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{name}"
    headers = {"Authorization": f"token {GH_TOKEN}"}

    content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()

    payload = {
        "message": "auto update",
        "content": content,
        "branch": "main"
    }

    if sha:
        payload["sha"] = sha

    requests.put(url, headers=headers, json=payload)

# ---------- UTENTI ----------
def get_utenti():
    utenti, sha = get_file(UTENTI_FILE)
    return utenti if isinstance(utenti, list) else [], sha

def save_utenti(data, sha):
    save_file(UTENTI_FILE, data, sha)

def handle_commands():
    utenti, sha = get_utenti()

    updates = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    ).json()

    for u in updates.get("result", []):
        msg = u.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "")

        if not chat_id:
            continue

        if text == "/start" and chat_id not in utenti:
            utenti.append(chat_id)
            save_utenti(utenti, sha)
            send(chat_id, "✅ Registrato")

        elif text == "/stop" and chat_id in utenti:
            utenti.remove(chat_id)
            save_utenti(utenti, sha)
            send(chat_id, "❌ Disiscritto")

    return utenti

# ---------- SCRAPER ----------
def scrape():
    prodotti = []

    for url in URLS:
        res = requests.get(url)
        soup = BeautifulSoup(res.text, "html.parser")

        for c in soup.select(".product"):
            nome = c.select_one("h2").text.strip()

            prezzo = 0
            p = c.select_one(".price")
            if p:
                prezzo = float(p.text.replace("€", "").replace(",", "."))

            disponibile = "esaurito" not in c.text.lower()

            prodotti.append({
                "nome": nome,
                "prezzo": prezzo,
                "disp": disponibile
            })

    return prodotti

# ---------- ROI ----------
def roi(prezzo):
    return round(((120 - prezzo) / prezzo) * 100, 2) if prezzo else 0

# ---------- MAIN ----------
def main():
    utenti = handle_commands()
    if not utenti:
        return

    storico, sha = get_file(STORICO_FILE)
    if not isinstance(storico, dict):
        storico = {}

    now = datetime.now()

    prodotti = scrape()

    alert = []

    for p in prodotti:
        nome = p["nome"]
        prezzo = p["prezzo"]
        disp = p["disp"]

        old = storico.get(nome)

        if not old or old["prezzo"] != prezzo or old["disp"] != disp:
            msg = f"📦 {nome}\n💰 {prezzo}€\n"
            msg += "✅ Disponibile\n" if disp else "❌ Esaurito\n"
            msg += f"📈 ROI: {roi(prezzo)}%"

            alert.append(msg)

        storico[nome] = {
            "prezzo": prezzo,
            "disp": disp,
            "time": now.isoformat()
        }

    # clean 24h
    storico = {
        k: v for k, v in storico.items()
        if now - datetime.fromisoformat(v["time"]) < timedelta(hours=24)
    }

    save_file(STORICO_FILE, storico, sha)

    # send alerts
    if alert:
        broadcast("🔥 AGGIORNAMENTI 🔥", utenti)
        for a in alert[:10]:
            broadcast(a, utenti)

    # heartbeat ogni ora
    if now.minute < 5:
        broadcast(f"💓 BOT ATTIVO\nProdotti: {len(prodotti)}", utenti)

if __name__ == "__main__":
    main()
