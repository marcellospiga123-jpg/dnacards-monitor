import requests
from bs4 import BeautifulSoup
import json
import time
import os
import base64

# ===== CONFIG =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO = "marcellospiga123-jpg/dna-dashboard"
FILE_PATH = "storico.json"

# ===== TELEGRAM =====
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except:
        print("Errore Telegram")

# ===== GITHUB LOAD =====
def load_github():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode()
        return json.loads(content), data["sha"]
    else:
        return {}, None

# ===== GITHUB SAVE =====
def save_github(data, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()

    payload = {
        "message": "update prezzi",
        "content": content,
        "sha": sha
    }

    requests.put(url, headers=headers, json=payload)

# ===== SCRAPER =====
def get_products():
    url = "https://www.dnacards.it/collections/one-piece"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")

    prodotti = []

    for item in soup.select(".grid-product"):
        nome = item.select_one(".grid-product__title").text.strip()
        
        prezzo = item.select_one(".grid-product__price").text.strip()
        prezzo = float(prezzo.replace("€", "").replace(",", "."))

        # CHECK ESAURITO
        disponibile = True
        if "Sold out" in item.text or "Esaurito" in item.text:
            disponibile = False

        prodotti.append({
            "nome": nome,
            "prezzo": prezzo,
            "disponibile": disponibile
        })

    return prodotti

# ===== MAIN =====
def main():
    storico, sha = load_github()

    prodotti = get_products()

    for p in prodotti:
        nome = p["nome"]
        prezzo = p["prezzo"]
        disponibile = p["disponibile"]

        if nome not in storico:
            storico[nome] = {
                "prezzo": prezzo,
                "disponibile": disponibile
            }
            continue

        # 🔥 CAMBIO PREZZO
        if prezzo != storico[nome]["prezzo"]:
            send_telegram(f"💰 PREZZO CAMBIATO\n{nome}\n{prezzo}€")

        # 🔥 ESAURITO
        if storico[nome]["disponibile"] and not disponibile:
            send_telegram(f"❌ ESAURITO\n{nome}")

        # 🔥 TORNATO DISPONIBILE
        if not storico[nome]["disponibile"] and disponibile:
            send_telegram(f"✅ DISPONIBILE DI NUOVO\n{nome}")

        storico[nome]["prezzo"] = prezzo
        storico[nome]["disponibile"] = disponibile

    save_github(storico, sha)

# LOOP
if __name__ == "__main__":
    main()
