import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import matplotlib.pyplot as plt

# ─── CONFIG ─────────────────────────────

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

PREZZO_TARGET = 80
DROP_FORTE = 0.85  # -15%

STORICO_FILE = "storico.json"
ALERT_FILE = "alert.json"

# ─── TELEGRAM ───────────────────────────

def send_msg(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text}
    )

def send_photo(path):
    with open(path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            files={"photo": f},
            data={"chat_id": TELEGRAM_CHAT_ID}
        )

# ─── FILE ───────────────────────────────

def load(name):
    if os.path.exists(name):
        with open(name, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save(name, data):
    with open(name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ─── UTILS ──────────────────────────────

def p_float(p):
    try:
        return float(p.replace("€","").replace(",","."))
    except:
        return None

# ─── SCRAPE ─────────────────────────────

def scrape():
    prodotti = []

    for url in URLS:
        r = requests.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        for c in soup.select("li.product"):
            nome = c.select_one(".woocommerce-loop-product__title")
            prezzo = c.select_one(".price .amount")

            nome = nome.text.strip() if nome else "N/D"
            prezzo = prezzo.text.strip() if prezzo else "0"

            link = c.select_one("a")["href"]

            prodotti.append({
                "nome": nome,
                "prezzo": prezzo,
                "link": link
            })

    return prodotti

# ─── STORICO ────────────────────────────

def update_history(storico, prodotti):
    now = datetime.now().strftime("%H:%M")

    for p in prodotti:
        nome = p["nome"]

        if nome not in storico:
            storico[nome] = []

        storico[nome].append({
            "t": now,
            "p": p["prezzo"]
        })

    return storico

# ─── ANALISI INTELLIGENTE ───────────────

def analyze(prodotti, storico, alerts):
    msgs = []

    for p in prodotti:
        nome = p["nome"]
        prezzo = p_float(p["prezzo"])

        if not prezzo:
            continue

        history = storico.get(nome, [])
        prezzi = [p_float(d["p"]) for d in history if p_float(d["p"])]

        # TARGET
        if prezzo <= PREZZO_TARGET:
            key = f"T_{nome}"
            if key not in alerts:
                msgs.append(f"🎯 TARGET\n{nome}\n{prezzo}€\n{p['link']}")
                alerts[key] = True

        # MINIMO STORICO
        if len(prezzi) > 2 and prezzo == min(prezzi):
            key = f"M_{nome}"
            if key not in alerts:
                msgs.append(f"🔥 MINIMO STORICO\n{nome}\n{prezzo}€")
                alerts[key] = True

        # CALO FORTE
        if len(prezzi) > 1 and prezzi[-1] < prezzi[-2] * DROP_FORTE:
            key = f"D_{nome}"
            if key not in alerts:
                msgs.append(f"📉 CROLLO\n{nome}\n{prezzo}€")
                alerts[key] = True

        # BEST DEAL (combo)
        if len(prezzi) > 3:
            avg = sum(prezzi[:-1]) / (len(prezzi)-1)
            if prezzo < avg * 0.8:
                key = f"B_{nome}"
                if key not in alerts:
                    msgs.append(f"💸 BEST DEAL\n{nome}\n{prezzo}€")
                    alerts[key] = True

    return msgs

# ─── GRAFICO ────────────────────────────

def make_graph(storico):
    plt.figure()

    i = 0
    for nome, dati in storico.items():
        if i >= 3:
            break

        prezzi = []
        for d in dati[-10:]:
            pf = p_float(d["p"])
            if pf:
                prezzi.append(pf)

        if len(prezzi) > 1:
            plt.plot(prezzi, label=nome[:15])
            i += 1

    if i == 0:
        return None

    plt.legend()
    file = "grafico.png"
    plt.savefig(file)
    plt.close()

    return file

# ─── MAIN ───────────────────────────────

def main():
    send_msg("🤖 BOT FINAL BOSS ONLINE")

    storico = load(STORICO_FILE)
    alerts = load(ALERT_FILE)

    prodotti = scrape()

    storico = update_history(storico, prodotti)

    msgs = analyze(prodotti, storico, alerts)

    for m in msgs:
        send_msg(m)

    g = make_graph(storico)
    if g:
        send_photo(g)

    save(STORICO_FILE, storico)
    save(ALERT_FILE, alerts)

# ─── RUN ────────────────────────────────

if __name__ == "__main__":
    main()
