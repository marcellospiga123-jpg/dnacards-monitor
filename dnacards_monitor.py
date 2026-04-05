import requests
from bs4 import BeautifulSoup
import json
import os
import base64
from datetime import datetime
import matplotlib.pyplot as plt
import statistics

# ================= CONFIG =================
URLS = {
    "JP": "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "EN": "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "SINGLE": "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
}

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

REPO = "marcellospiga123-jpg/dna-dashboard"
FILE = "storico.json"

# ================= TELEGRAM =================
def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        )
    except:
        print("Errore Telegram")

# ================= GITHUB =================
def load():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode()
        return json.loads(content), data["sha"]

    return {}, None

def save(data, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()

    body = {
        "message": "update prezzi",
        "content": content
    }

    if sha:
        body["sha"] = sha

    requests.put(url, headers=headers, json=body)

# ================= UTILS =================
def price(p):
    try:
        return float(p.replace("€","").replace(",","."))
    except:
        return None

# ================= SCRAPER =================
def scrape():
    prodotti = {}

    headers = {"User-Agent": "Mozilla/5.0"}

    for sito, url in URLS.items():
        try:
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            for p in soup.select("li.product"):
                nome = p.select_one(".woocommerce-loop-product__title")
                prezzo = p.select_one(".price .amount")

                if not nome:
                    continue

                nome = nome.text.strip()

                if prezzo:
                    prezzo_txt = prezzo.text.strip()
                else:
                    prezzo_txt = "OUT"

                prodotti.setdefault(nome, []).append({
                    "sito": sito,
                    "prezzo": prezzo_txt
                })

        except:
            continue

    return prodotti

# ================= ANALISI =================
def analisi(prodotti, storico):
    segnali = []

    for nome, varianti in prodotti.items():
        prezzi = [price(v["prezzo"]) for v in varianti if price(v["prezzo"])]

        if not prezzi:
            continue

        best = min(prezzi)
        hist = storico.get(nome, [])

        valori = [price(x["p"]) for x in hist if price(x["p"])]

        if len(valori) < 3:
            continue

        avg = sum(valori)/len(valori)
        max_p = max(valori)

        profit = max_p - best
        roi = profit / best if best else 0

        if profit > 10 and roi > 0.2:
            segnali.append(f"""
🔥 DEAL

{nome}

💰 Prezzo: {best}€
📈 Target: {round(max_p,2)}€
ROI: {round(roi*100,1)}%
""")

    return segnali

# ================= UPDATE =================
def update(storico, prodotti):
    t = datetime.now().strftime("%H:%M")

    for nome, varianti in prodotti.items():
        prezzi = [v for v in varianti if price(v["prezzo"])]

        if not prezzi:
            continue

        best = min(prezzi, key=lambda x: price(x["prezzo"]))

        storico.setdefault(nome, []).append({
            "t": t,
            "p": best["prezzo"]
        })

    return storico

# ================= GRAFICO =================
def grafico(storico):
    plt.figure()

    for nome, dati in list(storico.items())[:5]:
        prezzi = [price(d["p"]) for d in dati if price(d["p"])]
        if len(prezzi) > 1:
            plt.plot(prezzi, label=nome[:10])

    if not plt.gca().has_data():
        return

    plt.legend()
    plt.savefig("grafico.png")
    plt.close()

# ================= MAIN =================
def main():
    send("🤖 BOT ATTIVO")

    storico, sha = load()

    prodotti = scrape()
    storico = update(storico, prodotti)

    segnali = analisi(prodotti, storico)

    for s in segnali:
        send(s)

    if segnali:
        grafico(storico)

    save(storico, sha)

if __name__ == "__main__":
    main()
