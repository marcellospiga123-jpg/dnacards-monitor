"""
DNA Cards Monitor PRO
Monitora EN + JP + Bustine singole
Versione veloce (no Playwright)
"""

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

# ─── URL MULTIPLI ───────────────────────────────────

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ─── EMAIL ─────────────────────────────────────────

EMAIL_ATTIVA = True
EMAIL_MITTENTE = os.environ.get("EMAIL_MITTENTE", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_DESTINATARIO = os.environ.get("EMAIL_DESTINATARIO", "")

# ─── GIST ───────────────────────────────────────────

GIST_TOKEN = os.environ.get("GIST_TOKEN", "")
GIST_ID = os.environ.get("GIST_ID", "")
GIST_FILE = "dnacards_stato.json"

# ─── GIST FUNZIONI ──────────────────────────────────

def carica_stato():
    if not GIST_ID or not GIST_TOKEN:
        return {}
    try:
        r = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"token {GIST_TOKEN}"},
            timeout=10,
        )
        if r.ok:
            content = r.json()["files"].get(GIST_FILE, {}).get("content", "{}")
            return json.loads(content)
    except Exception as e:
        print(f"[!] Errore caricamento stato: {e}")
    return {}

def salva_stato(prodotti):
    if not GIST_ID or not GIST_TOKEN:
        return
    stato = {
        p["nome"]: {
            "prezzo": p["prezzo"],
            "disponibile": p["disponibile"]
        }
        for p in prodotti
    }
    try:
        requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"token {GIST_TOKEN}"},
            json={
                "files": {
                    GIST_FILE: {
                        "content": json.dumps(stato, ensure_ascii=False, indent=2)
                    }
                }
            },
            timeout=10,
        )
        print("✔ Stato salvato su Gist")
    except Exception as e:
        print(f"[!] Errore salvataggio stato: {e}")

# ─── SCRAPING MULTI PAGINA ──────────────────────────

def scrape_prodotti():
    prodotti = []

    for url in URLS:
        print(f"\n🔎 Controllo: {url}")

        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f"[!] Errore richiesta: {e}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("li.product")

        print(f"Trovati {len(cards)} prodotti")

        for card in cards:
            try:
                nome_el = card.select_one(".woocommerce-loop-product__title")
                nome = nome_el.text.strip() if nome_el else "N/D"

                # aggiungo tag pagina per distinguere
                nome = f"[{url.split('/')[-2]}] {nome}"

                prezzo_el = card.select_one("ins .amount") or card.select_one(".price .amount")
                prezzo = prezzo_el.text.strip() if prezzo_el else None

                out = card.select_one(".out-of-stock, .soldout, .button.disabled")
                disponibile = not bool(out)

                link_el = card.select_one("a")
                link = link_el["href"] if link_el else url

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo,
                    "disponibile": disponibile,
                    "link": link,
                })

            except Exception as e:
                print(f"[!] Errore prodotto: {e}")

    return prodotti

# ─── LOGICA ─────────────────────────────────────────

def confronta(nuovi, vecchi):
    variazioni = []

    for p in nuovi:
        nome = p["nome"]
        vecchio = vecchi.get(nome)

        if not vecchio:
            variazioni.append({"tipo": "nuovo", **p})
            continue

        if vecchio["prezzo"] != p["prezzo"]:
            variazioni.append({
                "tipo": "prezzo",
                "nome": nome,
                "vecchio": vecchio["prezzo"],
                "nuovo": p["prezzo"],
                "link": p["link"],
            })

        if vecchio["disponibile"] != p["disponibile"]:
            variazioni.append({
                "tipo": "stock",
                "nome": nome,
                "disponibile": p["disponibile"],
                "link": p["link"],
            })

    return variazioni

# ─── EMAIL ──────────────────────────────────────────

def invia_email(testo):
    try:
        msg = MIMEMultipart()
        msg["Subject"] = "DNA Cards Alert"
        msg["From"] = EMAIL_MITTENTE
        msg["To"] = EMAIL_DESTINATARIO

        msg.attach(MIMEText(testo, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_MITTENTE, EMAIL_PASSWORD)
            server.send_message(msg)

        print("✉️ Email inviata")

    except Exception as e:
        print(f"[!] Errore email: {e}")

# ─── MAIN ───────────────────────────────────────────

def main():
    print("🚀 Monitor PRO avviato...\n")

    prodotti = scrape_prodotti()

    if not prodotti:
        print("[!] Nessun prodotto trovato")
        return

    stato_vecchio = carica_stato()

    if not stato_vecchio:
        print("Primo avvio → salvo stato")
        salva_stato(prodotti)
        return

    variazioni = confronta(prodotti, stato_vecchio)

    if variazioni:
        print(f"⚠️ {len(variazioni)} variazioni")

        testo = json.dumps(variazioni, indent=2, ensure_ascii=False)
        print(testo)

        if EMAIL_ATTIVA:
            invia_email(testo)

        salva_stato(prodotti)
    else:
        print("✔ Nessuna variazione")

# ─── RUN ────────────────────────────────────────────

if __name__ == "__main__":
    main()
