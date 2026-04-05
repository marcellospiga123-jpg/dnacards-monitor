import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import matplotlib.pyplot as plt
import statistics

# ─── CONFIG ─────────────────────────────

URLS = {
    "EN": "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "JP": "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "SINGLE": "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
}

WATCHLIST = ["OP-05", "OP-06", "OP-07"]
TARGET_PRICE = 80

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

STORICO_FILE = "storico.json"
ALERT_FILE = "alert.json"
STOCK_FILE = "stock.json"
HEARTBEAT_FILE = "heartbeat.json"
MSG_FILE = "messages.json"

PROFIT_MIN = 20
ROI_MIN = 0.25
CONFIDENCE_MIN = 60
HEARTBEAT_HOURS = 3

# ─── TELEGRAM ───────────────────────────

def send_msg(text, log):
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text}
    ).json()

    try:
        log.append({
            "id": r["result"]["message_id"],
            "time": datetime.now().timestamp()
        })
    except:
        pass

def send_photo(path, log):
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
        files={"photo": open(path, "rb")},
        data={"chat_id": TELEGRAM_CHATGRAM_CHAT_ID}
    ).json()

    try:
        log.append({
            "id": r["result"]["message_id"],
            "time": datetime.now().timestamp()
        })
    except:
        pass

def delete_msg(msg_id):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "message_id": msg_id}
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
                nome_el = c.select_one(".woocommerce-loop-product__title")
                prezzo_el = c.select_one(".price .amount")

                if not nome_el or not prezzo_el:
                    continue

                nome = nome_el.text.strip()
                prezzo = prezzo_el.text.strip()

                out = c.select_one(".out-of-stock")
                disponibile = False if out else True

                prodotti.setdefault(nome, []).append({
                    "sito": sito,
                    "prezzo": prezzo,
                    "link": c.select_one("a")["href"],
                    "disponibile": disponibile
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

# ─── AI PREVISIONE ──────────────────────

def predict_price(valori):
    if len(valori) < 5:
        return None

    trend = valori[-1] - valori[0]
    slope = trend / len(valori)

    return round(valori[-1] + slope * 5, 2)

# ─── EBAY ───────────────────────────────

def get_ebay_price(nome):
    try:
        query = nome.replace(" ", "+")
        url = f"https://www.ebay.it/sch/i.html?_nkw={query}"

        headers = {"User-Agent": "Mozilla/5.0"}

        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        prezzi = []

        for p in soup.select(".s-item__price")[:10]:
            text = p.text.replace("€", "").replace(",", ".")
            try:
                val = float(text.split()[0])
                if 5 < val < 500:
                    prezzi.append(val)
            except:
                continue

        if prezzi:
            return round(sum(prezzi)/len(prezzi), 2)

    except:
        pass

    return None

# ─── STOCK ──────────────────────────────

def check_stock(prodotti, old_stock, log):
    new_stock = {}

    for nome, varianti in prodotti.items():
        disponibile = any(v["disponibile"] for v in varianti)
        new_stock[nome] = disponibile

        old = old_stock.get(nome)

        if old is None:
            continue

        if old != disponibile:
            if disponibile:
                send_msg(f"✅ TORNATO DISPONIBILE\n\n{nome}", log)
            else:
                send_msg(f"❌ ESAURITO\n\n{nome}", log)

    return new_stock

# ─── ANALISI COMPLETA ───────────────────

def analisi(prodotti, storico, alerts, log):
    segnali = []

    for nome, varianti in prodotti.items():
        is_watch = any(w in nome for w in WATCHLIST)

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

        pred = predict_price(valori)
        ebay_price = get_ebay_price(nome)

        profitto = (pred or max_p) - best_price
        roi = profitto / best_price if best_price else 0

        score = 0
        if best_price < avg: score += 25
        if roi > ROI_MIN: score += 25
        if pred and pred > avg: score += 15
        if is_watch: score += 15
        if ebay_price and best_price < ebay_price: score += 20

        # TARGET ALERT
        if best_price < TARGET_PRICE:
            send_msg(f"🎯 TARGET HIT\n{nome}\n💰 {best_price}€\n{best['link']}", log)

        if profitto >= PROFIT_MIN and score >= CONFIDENCE_MIN:
            key = f"Q_{nome}"

            if key not in alerts:
                qty = int(100 / best_price) if best_price else 1

                msg = (
                    f"🚨 AI TRADE\n\n"
                    f"{nome}\n\n"
                    f"💰 Prezzo: {best_price}€ ({best['sito']})\n"
                    f"🌐 eBay: {ebay_price}€\n"
                    f"🔮 Predizione: {pred}€\n"
                    f"📈 ROI: {round(roi*100,1)}%\n"
                    f"⚡ Score: {score}/100\n\n"
                    f"🧠 Compra ~{qty} → Profitto stimato: {round(qty*profitto,2)}€\n\n"
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

# ─── HEARTBEAT ──────────────────────────

def heartbeat(log):
    data = load(HEARTBEAT_FILE)
    now = datetime.now().timestamp()

    if now - data.get("last", 0) > HEARTBEAT_HOURS * 3600:
        send_msg("🤖 AI TRADER ONLINE", log)
        data["last"] = now
        save(HEARTBEAT_FILE, data)

# ─── CLEAN ──────────────────────────────

def clean_messages(log):
    now = datetime.now().timestamp()
    keep = []

    for m in log:
        if now - m["time"] > 86400:
            delete_msg(m["id"])
        else:
            keep.append(m)

    return keep

# ─── MAIN ───────────────────────────────

def main():
    storico = load(STORICO_FILE)
    alerts = load(ALERT_FILE)
    old_stock = load(STOCK_FILE)
    log = load(MSG_FILE)

    prodotti = scrape()
    storico = update(storico, prodotti)

    new_stock = check_stock(prodotti, old_stock, log)

    segnali = analisi(prodotti, storico, alerts, log)

    for s in segnali:
        send_msg(s, log)

    if segnali:
        g = grafico(storico)
        if g:
            send_photo(g, log)

    heartbeat(log)
    log = clean_messages(log)

    save(STORICO_FILE, storico)
    save(ALERT_FILE, alerts)
    save(STOCK_FILE, new_stock)
    save(MSG_FILE, log)

if __name__ == "__main__":
    main()
