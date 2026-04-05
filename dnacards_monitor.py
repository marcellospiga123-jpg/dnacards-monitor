import requests
import json
import time
import base64
import os

# ==============================
# CONFIG (usa Secrets GitHub)
# ==============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

REPO = "marcellospiga123-jpg/dna-dashboard"
FILE_PATH = "storico.json"

# ==============================
# TELEGRAM (CON DEBUG)
# ==============================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    
    try:
        r = requests.post(url, data=data)
        print("TELEGRAM RESPONSE:", r.text)
    except Exception as e:
        print("ERRORE TELEGRAM:", e)

# ==============================
# GITHUB LOAD SICURO
# ==============================
def load_github():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        data = r.json()

        # 🔥 FIX ERRORE content
        if "content" not in data:
            print("File vuoto o formato errato")
            return [], None

        content = base64.b64decode(data["content"]).decode()
        return json.loads(content), data["sha"]

    else:
        print("File non trovato, ne creo uno nuovo")
        return [], None

# ==============================
# GITHUB SAVE
# ==============================
def save_github(data, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()

    body = {
        "message": "update storico",
        "content": content,
        "sha": sha
    }

    requests.put(url, headers=headers, json=body)

# ==============================
# DATI FAKE (SIMULAZIONE)
# ==============================
def get_data():
    # Simula prezzi
    return [
        {"name": "Carta A", "price": 10 + int(time.time()) % 5},
        {"name": "Carta B", "price": 20 + int(time.time()) % 3},
    ]

# ==============================
# MAIN
# ==============================
def main():
    # 🔥 TEST TELEGRAM
    send_telegram("🚀 BOT AVVIATO CORRETTAMENTE")

    storico, sha = load_github()
    nuovi_dati = get_data()

    alert = False

    for item in nuovi_dati:
        for old in storico:
            if item["name"] == old["name"]:
                if item["price"] > old["price"]:
                    msg = f"📈 {item['name']} salita!\n{old['price']} → {item['price']}"
                    send_telegram(msg)
                    alert = True

    save_github(nuovi_dati, sha)

    if not alert:
        print("Nessun cambiamento")

# ==============================
# START
# ==============================
if __name__ == "__main__":
    main()
