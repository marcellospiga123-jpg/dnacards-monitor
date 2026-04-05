import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

# ─── URL ─────────────────────────────────────────────────────────────

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

# ─── EMAIL ───────────────────────────────────────────────────────────

EMAIL_ATTIVA       = True
EMAIL_MITTENTE     = os.environ.get("EMAIL_MITTENTE", "")
EMAIL_PASSWORD     = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_DESTINATARIO = os.environ.get("EMAIL_DESTINATARIO", "")

# ─── TELEGRAM ────────────────────────────────────────────────────────

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ─── GIST ────────────────────────────────────────────────────────────

GIST_TOKEN = os.environ.get("GIST_TOKEN", "")
GIST_ID    = os.environ.get("GIST_ID", "")
GIST_FILE  = "dnacards_stato.json"

# ─── STATO ───────────────────────────────────────────────────────────

def carica_stato():
    if not GIST_ID or not GIST_TOKEN:
        return {}
    try:
        r = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"token {GIST_TOKEN}"},
        )
        if r.ok:
            content = r.json()["files"].get(GIST_FILE, {}).get("content", "{}")
            return json.loads(content)
    except:
        pass
    return {}

def salva_stato(prodotti):
    if not GIST_ID or not GIST_TOKEN:
        return
    stato = {p["nome"]: {"prezzo": p["prezzo"], "disponibile": p["disponibile"]} for p in prodotti}
    requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GIST_TOKEN}"},
        json={"files": {GIST_FILE: {"content": json.dumps(stato, indent=2)}}},
    )

# ─── SCRAPING VELOCE ────────────────────────────────────────────────

def scrape():
    prodotti = []

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for url in URLS:
        print(f"Controllo: {url}")

        r = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        cards = soup.select("li.product")

        for card in cards:
            try:
                nome = card.select_one(".woocommerce-loop-product__title")
                nome = nome.text.strip() if nome else "N/D"

                prezzo = card.select_one(".price .amount")
                prezzo = prezzo.text.strip() if prezzo else "N/D"

                disponibile = not card.select_one(".out-of-stock")

                link = card.select_one("a")["href"]

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo,
                    "disponibile": disponibile,
                    "link": link
                })
            except:
                pass

    return prodotti

# ─── CONFRONTO ──────────────────────────────────────────────────────

def confronta(nuovi, vecchi):
    variazioni = []

    for p in nuovi:
        nome = p["nome"]
        old = vecchi.get(nome)

        if not old:
            variazioni.append({"tipo": "nuovo", **p})
            continue

        if old["prezzo"] != p["prezzo"]:
            variazioni.append({
                "tipo": "prezzo",
                "nome": nome,
                "vecchio": old["prezzo"],
                "nuovo": p["prezzo"],
                "link": p["link"]
            })

        if old["disponibile"] != p["disponibile"]:
            variazioni.append({
                "tipo": "stock",
                "nome": nome,
                "disponibile": p["disponibile"],
                "link": p["link"]
            })

    return variazioni

# ─── FORMAT (BONUS BELLO 🔥) ─────────────────────────────────────────

def formatta(variazioni):
    testo = "🔔 DNA Cards Alert\n\n"

    for v in variazioni:
        if v["tipo"] == "prezzo":
            testo += f"💰 PREZZO: {v['nome']}\n"
            testo += f"{v['vecchio']} → {v['nuovo']}\n"
            testo += f"{v['link']}\n\n"

        elif v["tipo"] == "stock":
            stato = "✅ Disponibile" if v["disponibile"] else "❌ Esaurito"
            testo += f"📦 STOCK: {v['nome']}\n"
            testo += f"{stato}\n"
            testo += f"{v['link']}\n\n"

        elif v["tipo"] == "nuovo":
            testo += f"🆕 NUOVO: {v['nome']}\n"
            testo += f"{v.get('prezzo', 'N/D')}\n"
            testo += f"{v['link']}\n\n"

    return testo

# ─── EMAIL ──────────────────────────────────────────────────────────

def invia_email(testo):
    try:
        msg = MIMEMultipart()
        msg["Subject"] = "DNA Cards Update"
        msg["From"] = EMAIL_MITTENTE
        msg["To"] = EMAIL_DESTINATARIO

        msg.attach(MIMEText(testo, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_MITTENTE, EMAIL_PASSWORD)
            server.sendmail(EMAIL_MITTENTE, EMAIL_DESTINATARIO, msg.as_string())

        print("Email inviata")
    except Exception as e:
        print("Errore email:", e)

# ─── TELEGRAM ───────────────────────────────────────────────────────

def invia_telegram(testo):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": testo,
                "parse_mode": "HTML"
            },
            timeout=10
        )
        print("Telegram inviato")
    except Exception as e:
        print("Errore telegram:", e)

# ─── MAIN ───────────────────────────────────────────────────────────

def main():
    print("Controllo...")

    prodotti = scrape()
    stato = carica_stato()

    if not stato:
        salva_stato(prodotti)
        print("Primo avvio")
        return

    var = confronta(prodotti, stato)

    if var:
        msg = formatta(var)
        print(msg)
        invia_email(msg)
        invia_telegram(msg)
        salva_stato(prodotti)
    else:
        print("Nessuna variazione")

if __name__ == "__main__":
    main()
