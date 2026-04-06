import requests
from bs4 import BeautifulSoup
import time
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

storico = {}
messaggi = []
last_heartbeat = 0
last_cleanup = time.time()

# ---------------- TELEGRAM ---------------- #

def send(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": msg
        }, timeout=10)

        if r.status_code == 200:
            msg_id = r.json()["result"]["message_id"]
            messaggi.append(msg_id)

    except Exception as e:
        print("Errore invio telegram:", e)

def delete_all():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"

    for m in messaggi:
        try:
            requests.post(url, data={
                "chat_id": CHAT_ID,
                "message_id": m
            }, timeout=5)
        except:
            pass

    messaggi.clear()

# ---------------- SCRAPER ---------------- #

def scrape():
    prodotti = []

    for url in URLS:
        try:
            res = requests.get(url, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")

            cards = soup.select(".product")

            for c in cards:
                nome = c.select_one("h2").text.strip()

                prezzo_tag = c.select_one(".price")
                prezzo = 0

                if prezzo_tag:
                    prezzo = float(
                        prezzo_tag.text
                        .replace("€", "")
                        .replace(",", ".")
                        .strip()
                    )

                disponibile = "Esaurito" not in c.text

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo,
                    "disponibile": disponibile
                })

        except Exception as e:
            print("Errore scraping:", e)

    print(f"PRODOTTI TROVATI: {len(prodotti)}")
    return prodotti

# ---------------- LOGICA ---------------- #

def check(prodotti):
    global storico

    for p in prodotti:
        nome = p["nome"]

        if nome not in storico:
            storico[nome] = p

            send(f"🆕 NUOVO\n{nome}\n💰 {p['prezzo']}€")

        else:
            old = storico[nome]

            # prezzo
            if p["prezzo"] != old["prezzo"]:
                diff = round(p["prezzo"] - old["prezzo"], 2)

                send(
                    f"💸 PREZZO CAMBIATO\n{nome}\n"
                    f"{old['prezzo']}€ ➜ {p['prezzo']}€\n"
                    f"ROI: {diff}€"
                )

            # disponibilità
            if p["disponibile"] != old["disponibile"]:
                stato = "🟢 DISPONIBILE" if p["disponibile"] else "🔴 ESAURITO"
                send(f"{stato}\n{nome}")

            storico[nome] = p

# ---------------- HEARTBEAT ---------------- #

def heartbeat():
    global last_heartbeat

    now = time.time()

    if now - last_heartbeat > 900:
        send("💓 BOT ATTIVO")
        last_heartbeat = now

# ---------------- MAIN ---------------- #

def main():
    global last_cleanup

    send("🚀 BOT AVVIATO")

    while True:
        try:
            prodotti = scrape()
            check(prodotti)
            heartbeat()

            # cleanup ogni 24h
            if time.time() - last_cleanup > 86400:
                delete_all()
                last_cleanup = time.time()
                send("🧹 Pulizia completata")

        except Exception as e:
            send(f"❌ ERRORE: {e}")

        time.sleep(60)

if __name__ == "__main__":
    main()
