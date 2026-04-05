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

STATO_FILE = "stato.json"
STORICO_FILE = "storico.json"

# ─── TELEGRAM ───────────────────────────

def invia_telegram(testo):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram non configurato")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": testo
    })

def invia_foto(path, caption="📊 Grafico prezzi"):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"

    with open(path, "rb") as f:
        requests.post(url, files={"photo": f}, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption
        })

# ─── FILE ───────────────────────────────

def carica(nome):
    if os.path.exists(nome):
        with open(nome, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salva(nome, dati):
    with open(nome, "w", encoding="utf-8") as f:
        json.dump(dati, f, indent=2, ensure_ascii=False)

# ─── SCRAPING ───────────────────────────

def scrape():
    prodotti = []

    for url in URLS:
        try:
            r = requests.get(url, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            cards = soup.select("li.product")

            for c in cards:
                nome = c.select_one(".woocommerce-loop-product__title")
                prezzo = c.select_one(".price .amount")

                nome = nome.text.strip() if nome else "N/D"
                prezzo = prezzo.text.strip() if prezzo else "0"

                disponibile = not bool(c.select_one(".out-of-stock"))

                link = c.select_one("a")
                link = link["href"] if link else url

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo,
                    "disponibile": disponibile,
                    "link": link,
                    "sito": url
                })

        except Exception as e:
            print("Errore:", e)

    return prodotti

# ─── STORICO ────────────────────────────

def aggiorna_storico(storico, prodotti):
    now = datetime.now().strftime("%d/%m %H:%M")

    for p in prodotti:
        nome = p["nome"]

        if nome not in storico:
            storico[nome] = []

        storico[nome].append({
            "data": now,
            "prezzo": p["prezzo"]
        })

    return storico

# ─── CONFRONTO ──────────────────────────

def confronta(nuovi, vecchi):
    variazioni = []

    for p in nuovi:
        nome = p["nome"]
        old = vecchi.get(nome)

        if not old:
            variazioni.append({"tipo": "NUOVO", "nome": nome, "prezzo": p["prezzo"], "link": p["link"]})
            continue

        if old["prezzo"] != p["prezzo"]:
            variazioni.append({"tipo": "PREZZO", "nome": nome, "nuovo": p["prezzo"], "link": p["link"]})

        if old["disponibile"] != p["disponibile"]:
            tipo = "DISPONIBILE" if p["disponibile"] else "ESAURITO"
            variazioni.append({"tipo": tipo, "nome": nome, "prezzo": p["prezzo"], "link": p["link"]})

    return variazioni

# ─── FORMAT ─────────────────────────────

def formatta(variazioni):
    testo = "🔔 DNA Cards Alert\n\n"

    for v in variazioni:
        testo += f"{v['tipo']}: {v['nome']}\n"
        testo += f"{v.get('nuovo', v.get('prezzo', ''))}\n"
        testo += f"{v['link']}\n\n"

    return testo

# ─── SCONTI ─────────────────────────────

def trova_sconti(storico):
    msg = []

    for nome, dati in storico.items():
        if len(dati) < 2:
            continue

        try:
            p1 = float(dati[-2]["prezzo"].replace("€","").replace(",","."))
            p2 = float(dati[-1]["prezzo"].replace("€","").replace(",","."))

            if p2 < p1:
                msg.append(f"📉 SCONTO: {nome}\n{p1}€ → {p2}€")
        except:
            continue

    return msg

# ─── MINIMO STORICO ─────────────────────

def minimo_storico(storico):
    msg = []

    for nome, dati in storico.items():
        prezzi = []

        for d in dati:
            try:
                prezzi.append(float(d["prezzo"].replace("€","").replace(",",".")))
            except:
                continue

        if len(prezzi) < 2:
            continue

        if prezzi[-1] == min(prezzi):
            msg.append(f"🔥 PREZZO MINIMO: {nome}\n{prezzi[-1]}€")

    return msg

# ─── CONFRONTO SITI ─────────────────────

def confronto_siti(prodotti):
    best = {}

    for p in prodotti:
        nome = p["nome"]

        try:
            prezzo = float(p["prezzo"].replace("€","").replace(",","."))
        except:
            continue

        if nome not in best or prezzo < best[nome]["prezzo"]:
            best[nome] = {"prezzo": prezzo, "link": p["link"]}

    msg = []
    for nome, d in best.items():
        msg.append(f"🏆 MIGLIOR PREZZO: {nome}\n{d['prezzo']}€\n{d['link']}")

    return msg[:3]

# ─── GRAFICO PRO ────────────────────────

def grafico_pro(storico):
    plt.figure(figsize=(10,5))

    count = 0

    for nome, dati in storico.items():
        if count >= 3:
            break

        prezzi = []
        date = []

        for d in dati[-10:]:
            try:
                prezzi.append(float(d["prezzo"].replace("€","").replace(",",".")))
                date.append(d["data"])
            except:
                continue

        if len(prezzi) < 2:
            continue

        plt.plot(date, prezzi, marker='o', label=nome[:20])
        count += 1

    if count == 0:
        return None

    plt.xticks(rotation=45)
    plt.title("📊 Andamento Prezzi")
    plt.legend()
    plt.tight_layout()

    file = "grafico.png"
    plt.savefig(file)
    plt.close()

    return file

# ─── MAIN ───────────────────────────────

def main():
    print("START BOT")

    invia_telegram("✅ BOT ONLINE")

    stato_vecchio = carica(STATO_FILE)
    storico = carica(STORICO_FILE)

    prodotti = scrape()

    stato_nuovo = {
        p["nome"]: {
            "prezzo": p["prezzo"],
            "disponibile": p["disponibile"]
        } for p in prodotti
    }

    variazioni = confronta(prodotti, stato_vecchio)

    if variazioni:
        invia_telegram(formatta(variazioni))

    storico = aggiorna_storico(storico, prodotti)

    # ALERT EXTRA
    for msg in trova_sconti(storico):
        invia_telegram(msg)

    for msg in minimo_storico(storico):
        invia_telegram(msg)

    for msg in confronto_siti(prodotti):
        invia_telegram(msg)

    # GRAFICO
    g = grafico_pro(storico)
    if g:
        invia_foto(g)

    salva(STATO_FILE, stato_nuovo)
    salva(STORICO_FILE, storico)

    print("END")

# ─── RUN ────────────────────────────────

if __name__ == "__main__":
    main()
