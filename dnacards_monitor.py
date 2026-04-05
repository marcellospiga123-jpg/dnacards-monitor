import json
import os
import requests
from bs4 import BeautifulSoup

# ─── CONFIG ─────────────────────────────────────────

URLS = [
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID = os.environ.get("GIST_ID")
GIST_FILE = "dnacards_stato.json"

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ─── TELEGRAM ───────────────────────────────────────

def invia_telegram(variazioni):
    for v in variazioni:
        testo = f"🔔 *{v['tipo'].upper()}*\n\n"
        testo += f"📦 {v['nome']}\n"
        testo += f"💰 {v.get('prezzo', v.get('prezzo_nuovo', 'N/D'))}\n"

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": testo,
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [[
                    {
                        "text": "🔗 Apri prodotto",
                        "url": v["link"]
                    }
                ]]
            }
        }

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json=payload
        )

# ─── GIST ───────────────────────────────────────────

def carica_stato():
    if not GIST_ID:
        return {}
    r = requests.get(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GIST_TOKEN}"}
    )
    if r.ok:
        content = r.json()["files"].get(GIST_FILE, {}).get("content", "{}")
        return json.loads(content)
    return {}

def salva_stato(prodotti):
    stato = {p["nome"]: p for p in prodotti}
    requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GIST_TOKEN}"},
        json={
            "files": {
                GIST_FILE: {
                    "content": json.dumps(stato, indent=2, ensure_ascii=False)
                }
            }
        }
    )

# ─── SCRAPER ────────────────────────────────────────

def scrape():
    prodotti = []

    for URL in URLS:
        print(f"Controllo: {URL}")

        r = requests.get(URL, headers=HEADERS)
        soup = BeautifulSoup(r.text, "html.parser")

        cards = soup.select("li.product")

        for c in cards:
            nome = c.select_one(".woocommerce-loop-product__title")
            nome = nome.text.strip() if nome else "N/D"

            prezzo = c.select_one(".price")
            prezzo = prezzo.text.strip() if prezzo else "N/D"

            link = c.select_one("a")
            link = link["href"] if link else URL

            disponibile = not c.select_one(".out-of-stock")

            prodotti.append({
                "nome": nome,
                "prezzo": prezzo,
                "disponibile": disponibile,
                "link": link
            })

    return prodotti

# ─── CONFRONTO ──────────────────────────────────────

def confronta(nuovi, vecchi):
    variazioni = []

    for p in nuovi:
        nome = p["nome"]
        v = vecchi.get(nome)

        if not v:
            variazioni.append({**p, "tipo": "nuovo"})
            continue

        if v["prezzo"] != p["prezzo"]:
            variazioni.append({
                **p,
                "tipo": "prezzo",
                "prezzo_vecchio": v["prezzo"],
                "prezzo_nuovo": p["prezzo"]
            })

        if v["disponibile"] != p["disponibile"]:
            tipo = "disponibile" if p["disponibile"] else "esaurito"
            variazioni.append({**p, "tipo": tipo})

    return variazioni

# ─── MAIN ───────────────────────────────────────────

def main():
    print("Monitor avviato...")

    nuovi = scrape()
    vecchi = carica_stato()

    if not vecchi:
        print("Primo avvio → salvo stato")
        salva_stato(nuovi)
        return

    variazioni = confronta(nuovi, vecchi)

    if variazioni:
        print("⚠️ Cambiamenti trovati!")
        invia_telegram(variazioni)
        salva_stato(nuovi)
    else:
        print("Nessuna variazione")

if __name__ == "__main__":
    main()
