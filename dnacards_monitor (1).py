"""
DNA Cards - Monitor prezzi e disponibilità
Versione per GitHub Actions — stato salvato su GitHub Gist
"""

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

import requests
from playwright.sync_api import sync_playwright

# ─── CONFIGURAZIONE ───────────────────────────────────────────────────────────

URL = "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/"

EMAIL_ATTIVA = True
EMAIL_MITTENTE = os.environ.get("marcellospiga123@gmail.com", "")
EMAIL_PASSWORD = os.environ.get("hgwobgaymsgqnebf", "")
EMAIL_DESTINATARIO = os.environ.get("marcellospiga123@gmail.com", "")
EMAIL_SMTP = "smtp.gmail.com"
EMAIL_PORT = 587

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GIST_ID = os.environ.get("GIST_ID", "")
GIST_FILENAME = "dnacards_stato.json"

# ─── GIST (memoria persistente) ──────────────────────────────────────────────

def carica_stato_da_gist():
    if not GIST_ID or not GITHUB_TOKEN:
        return {}
    try:
        r = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
            timeout=10
        )
        if r.ok:
            contenuto = r.json()["files"].get(GIST_FILENAME, {}).get("content", "{}")
            return json.loads(contenuto)
    except Exception as e:
        print(f"  [!] Errore lettura Gist: {e}")
    return {}

def salva_stato_su_gist(prodotti):
    if not GIST_ID or not GITHUB_TOKEN:
        return
    stato = {p["nome"]: {"prezzo": p["prezzo"], "disponibile": p["disponibile"]} for p in prodotti}
    try:
        r = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"token {GITHUB_TOKEN}"},
            json={"files": {GIST_FILENAME: {"content": json.dumps(stato, ensure_ascii=False, indent=2)}}},
            timeout=10
        )
        if r.ok:
            print("  Stato salvato su Gist.")
        else:
            print(f"  [!] Errore salvataggio Gist: {r.text}")
    except Exception as e:
        print(f"  [!] Errore salvataggio Gist: {e}")

# ─── SCRAPING ────────────────────────────────────────────────────────────────

def scrape_prodotti():
    prodotti = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0"})
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        cards = page.query_selector_all("li.product")
        for card in cards:
            try:
                nome_el = card.query_selector(".woocommerce-loop-product__title")
                nome = nome_el.inner_text().strip() if nome_el else "N/D"

                prezzo = None
                ins_el = card.query_selector("ins .amount")
                if ins_el:
                    prezzo = ins_el.inner_text().strip()
                else:
                    price_el = card.query_selector(".price .amount")
                    if price_el:
                        prezzo = price_el.inner_text().strip()

                esaurito_el = card.query_selector(".out-of-stock, .soldout, .button.disabled")
                in_stock = True
                if esaurito_el:
                    in_stock = False
                else:
                    add_btn = card.query_selector("a.add_to_cart_button, button.single_add_to_cart_button")
                    if not add_btn:
                        in_stock = False

                link_el = card.query_selector("a.woocommerce-loop-product__link, a")
                link = link_el.get_attribute("href") if link_el else URL

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo,
                    "disponibile": in_stock,
                    "link": link,
                })
            except Exception as e:
                print(f"  [!] Errore su un prodotto: {e}")

        browser.close()
    return prodotti

# ─── CONFRONTO ───────────────────────────────────────────────────────────────

def confronta(prodotti_nuovi, stato_vecchio):
    variazioni = []
    for p in prodotti_nuovi:
        nome = p["nome"]
        vecchio = stato_vecchio.get(nome)

        if vecchio is None:
            variazioni.append({"tipo": "nuovo", "nome": nome, "prezzo": p["prezzo"], "disponibile": p["disponibile"], "link": p["link"]})
            continue

        if vecchio["prezzo"] != p["prezzo"]:
            variazioni.append({"tipo": "prezzo", "nome": nome, "prezzo_vecchio": vecchio["prezzo"], "prezzo_nuovo": p["prezzo"], "disponibile": p["disponibile"], "link": p["link"]})

        if vecchio["disponibile"] != p["disponibile"]:
            tipo = "tornato_disponibile" if p["disponibile"] else "esaurito"
            variazioni.append({"tipo": tipo, "nome": nome, "prezzo": p["prezzo"], "link": p["link"]})

    return variazioni

# ─── NOTIFICHE ───────────────────────────────────────────────────────────────

def formatta_messaggio(variazioni):
    righe = [f"DNA Cards — {len(variazioni)} variazione/i rilevata/e\n"]
    for v in variazioni:
        if v["tipo"] == "prezzo":
            righe.append(f"PREZZO CAMBIATO: {v['nome']}\n{v['prezzo_vecchio']} -> {v['prezzo_nuovo']}\n{v['link']}")
        elif v["tipo"] == "esaurito":
            righe.append(f"ESAURITO: {v['nome']}\nPrezzo: {v.get('prezzo', 'N/D')}\n{v['link']}")
        elif v["tipo"] == "tornato_disponibile":
            righe.append(f"TORNATO DISPONIBILE: {v['nome']}\nPrezzo: {v.get('prezzo', 'N/D')}\n{v['link']}")
        elif v["tipo"] == "nuovo":
            stato = "Disponibile" if v["disponibile"] else "Esaurito"
            righe.append(f"NUOVO PRODOTTO: {v['nome']}\nPrezzo: {v.get('prezzo', 'N/D')} - {stato}\n{v['link']}")
    return "\n\n".join(righe)

def invia_email(testo):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "DNA Cards — Variazione prezzo/disponibilita"
        msg["From"] = EMAIL_MITTENTE
        msg["To"] = EMAIL_DESTINATARIO
        msg.attach(MIMEText(testo, "plain", "utf-8"))
        with smtplib.SMTP(EMAIL_SMTP, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_MITTENTE, EMAIL_PASSWORD)
            server.sendmail(EMAIL_MITTENTE, EMAIL_DESTINATARIO, msg.as_string())
        print("  Email inviata.")
    except Exception as e:
        print(f"  [!] Errore email: {e}")

def invia_notifiche(variazioni):
    if not variazioni:
        return
    testo = formatta_messaggio(variazioni)
    print(testo)
    if EMAIL_ATTIVA:
        invia_email(testo)

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    ora = datetime.now().strftime("%H:%M:%S")
    print(f"[{ora}] DNA Cards Monitor — controllo in corso...")

    try:
        prodotti = scrape_prodotti()
        print(f"Trovati {len(prodotti)} prodotti.")

        stato_vecchio = carica_stato_da_gist()

        if not stato_vecchio:
            print("Primo avvio: salvo stato iniziale. Le notifiche partiranno dal prossimo controllo.")
            salva_stato_su_gist(prodotti)
        else:
            variazioni = confronta(prodotti, stato_vecchio)
            if variazioni:
                print(f"{len(variazioni)} variazione/i rilevata/e!")
                invia_notifiche(variazioni)
                salva_stato_su_gist(prodotti)
            else:
                print("Nessuna variazione.")

    except Exception as e:
        print(f"[ERRORE] {e}")
        raise

if __name__ == "__main__":
    main()
