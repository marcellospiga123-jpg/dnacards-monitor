import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import matplotlib.pyplot as plt
import statistics
import base64

# ─── CONFIG ─────────────────────────────

URLS = {
    "EN": "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "JP": "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "SINGLE": "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
}

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

GITHUB_TOKEN = os.environ.get("GH_TOKEN")
REPO = os.environ.get("REPO")

FILE_NAME = "storico.json"

PROFIT_MIN = 20
ROI_MIN = 0.25
CONFIDENCE_MIN = 60

# ─── TELEGRAM ───────────────────────────

def send_msg(text):
    if not TELEGRAM_TOKEN:
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text}
    )

def send_photo(path):
    if not TELEGRAM_TOKEN:
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
        files={"photo": open(path, "rb")},
        data={"chat_id": TELEGRAM_CHAT_ID}
    )

# ─── GITHUB STORAGE ─────────────────────

def load_github():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode()
        return json.loads(content), data["sha"]
    
    # file non esiste ancora
    return {}, None

def save_github(data, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_NAME}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()

    payload = {
        "message": "update storico",
        "content": content
    }

    if sha:
        payload["sha"] = sha

    requests.put(url, headers=headers, json=payload)

# ─── UTILS ──────────────────────────────

def p_float(p):
    try:
        return float(p.replace("€","").replace(",","."))
    except:
        return None

# ─── SCRAPE ─────────────────────────────

def scrape():
    prodotti = {}

    for sito, url in URLS.items():
        try:
            r = requests.get(url)
            soup = BeautifulSoup(r.text, "html.parser")

            for c in soup.select("li.product"):
                nome = c.select_one(".woocommerce-loop-product__title")
                prezzo = c.select_one(".price .amount")

                if not nome or not prezzo:
                    continue

                nome = nome.text.strip()

                prodotti.setdefault(nome, []).append({
                    "sito": sito,
                    "prezzo": prezzo.text.strip(),
                    "link": c.select_one("a")["href"]
                })
        except:
            continue

    return prodotti

# ─── STORICO ────────────────────────────

def update(storico, prodotti):
    t = datetime.now().strftime("%H:%M")

    for nome, varianti in prodotti.items():
        best = min(varianti, key=lambda x: p_float(x["prezzo"]) or 9999)

        storico.setdefault(nome, []).append({
            "t": t,
            "p": best["prezzo"]
        })

    return storico

# ─── ANALISI ────────────────────────────

def analisi(prodotti, storico):
    segnali = []

    for nome, varianti in prodotti.items():
        prezzi = [(p_float(v["prezzo"]), v) for v in varianti if p_float(v["prezzo"])]

        if not prezzi:
            continue

        best_price, best = min(prezzi, key=lambda x: x[0])

        hist = storico.get(nome, [])
        valori = [p_float(x["p"]) for x in hist if p_float(x["p"])]

        if len(valori) < 5:
            continue

        avg = sum(valori) / len(valori)
        max_p = max(valori)

        profitto = max_p - best_price
        roi = profitto / best_price if best_price else 0

        trend = valori[-1] - valori[-3]
        vol = statistics.stdev(valori) if len(valori) > 2 else 0

        score = 0
        if best_price < avg: score += 30
        if roi > ROI_MIN: score += 30
        if trend >= 0: score += 20
        if vol < avg * 0.2: score += 20

        if profitto >= PROFIT_MIN and score >= CONFIDENCE_MIN:
            msg = (
                f"🚨 QUANT TRADE\n\n"
                f"{nome}\n\n"
                f"🏪 Prezzo: {best_price}€ ({best['sito']})\n"
                f"📈 Target: {round(max_p,2)}€\n"
                f"💸 Profitto: {round(profitto,2)}€\n"
                f"📊 ROI: {round(roi*100,1)}%\n"
                f"⚡ Score: {score}/100\n\n"
                f"{best['link']}"
            )

            segnali.append(msg)

    return segnali

# ─── GRAFICO ────────────────────────────

def grafico(storico):
    plt.figure()

    for nome, dati in list(storico.items())[:5]:
        prezzi = [p_float(d["p"]) for d in dati if p_float(d["p"])]
        if len(prezzi) > 1:
            plt.plot(prezzi, label=nome[:10])

    if not plt.gca().has_data():
        return None

    plt.legend()
    file = "grafico.png"
    plt.savefig(file)
    plt.close()

    return file

# ─── MAIN ───────────────────────────────

def main():
    storico, sha = load_github()

    prodotti = scrape()
    storico = update(storico, prodotti)

    segnali = analisi(prodotti, storico)

    for s in segnali:
        send_msg(s)

    if segnali:
        g = grafico(storico)
        if g:
            send_photo(g)

    save_github(storico, sha)

if __name__ == "__main__":
    main()
