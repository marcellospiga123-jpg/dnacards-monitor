import requests
from bs4 import BeautifulSoup
import json
import os
import base64
from datetime import datetime
import matplotlib.pyplot as plt
import statistics

# ─── CONFIG ─────────────────────────────

URLS = {
    "EN": "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "JP": "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "SINGLE": "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
}

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

GITHUB_TOKEN = "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"
REPO = "marcello123/dna-dashboard"
FILE_PATH = "storico.json"

ALERT_FILE = "alert.json"

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

# ─── FILE ───────────────────────────────

def load(name):
    if os.path.exists(name):
        with open(name) as f:
            return json.load(f)
    return {}

def save(name, data):
    with open(name, "w") as f:
        json.dump(data, f, indent=2)

# ─── GITHUB ─────────────────────────────

def load_github():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    r = requests.get(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}).json()

    content = base64.b64decode(r["content"]).decode()
    return json.loads(content), r["sha"]

def upload_github(data, sha):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"

    content = base64.b64encode(json.dumps(data, indent=2).encode()).decode()

    requests.put(url,
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        json={
            "message": "update storico prezzi",
            "content": content,
            "sha": sha
        }
    )

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

def analisi(prodotti, storico, alerts):
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
            key = f"Q_{nome}"

            if key not in alerts:
                qty = int(100 / best_price) if best_price else 1

                msg = (
                    f"🚨 QUANT TRADE\n\n"
                    f"{nome}\n\n"
                    f"🏪 Miglior prezzo: {best_price}€ ({best['sito']})\n"
                    f"📈 Target: {round(max_p,2)}€\n"
                    f"💸 Profitto/unità: {round(profitto,2)}€\n"
                    f"📊 ROI: {round(roi*100,1)}%\n"
                    f"⚡ Score: {score}/100\n\n"
                    f"🧠 Compra ~{qty} pezzi\n\n"
                    f"{best['link']}"
                )

                segnali.append(msg)
                alerts[key] = True

    return segnali

# ─── GRAFICO ────────────────────────────

def grafico(storico):
    plt.figure()

    for nome, dati in list(storico.items())[:5]:
        prezzi = [p_float(d["p"]) for d in dati if p_float(d["p"])]
        if len(prezzi) > 1:
            plt.plot(prezzi, label=nome[:12])

    if not plt.gca().has_data():
        return None

    plt.legend()
    file = "grafico.png"
    plt.savefig(file)
    plt.close()

    return file

# ─── MAIN ───────────────────────────────

def main():
    alerts = load(ALERT_FILE)

    prodotti = scrape()

    # 🔥 prende storico da GitHub
    storico, sha = load_github()

    storico = update(storico, prodotti)

    segnali = analisi(prodotti, storico, alerts)

    for s in segnali:
        send_msg(s)

    if segnali:
        g = grafico(storico)
        if g:
            send_photo(g)

    save(ALERT_FILE, alerts)

    # 🔥 salva su GitHub
    upload_github(storico, sha)

if __name__ == "__main__":
    main()
