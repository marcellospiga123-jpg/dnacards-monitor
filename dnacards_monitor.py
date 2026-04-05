import json
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import matplotlib.pyplot as plt

# ─── CONFIG ─────────────────────────────────────────

URLS = {
    "EN Display": "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/",
    "JP Display": "https://dnacards.it/categoria/one-piece/display-buste-one-piece-jp/",
    "EN Singole": "https://dnacards.it/categoria/one-piece/bustine-singole-one-piece-en/"
}

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID = os.environ.get("GIST_ID")
GIST_FILE = "dnacards_stato.json"

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ─── TELEGRAM ───────────────────────────────────────

def invia_telegram(testo, link=None):
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": testo,
        "parse_mode": "Markdown"
    }

    if link:
        payload["reply_markup"] = {
            "inline_keyboard": [[
                {"text": "🔗 Apri prodotto", "url": link}
            ]]
        }

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json=payload
    )

def invia_foto(file_path):
    with open(file_path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={"chat_id": TELEGRAM_CHAT_ID},
            files={"photo": f}
        )

# ─── GRAFICO ────────────────────────────────────────

def genera_grafico(nome, storico):
    prezzi, date = [], []

    for s in storico[-10:]:
        try:
            p = float(s["prezzo"].replace("€", "").replace(",", "."))
            prezzi.append(p)
            date.append(s["data"])
        except:
            continue

    if len(prezzi) < 2:
        return None

    plt.figure()
    plt.plot(prezzi)
    plt.title(nome)
    plt.xticks(range(len(date)), date, rotation=45)
    plt.tight_layout()

    file = "grafico.png"
    plt.savefig(file)
    plt.close()

    return file

# ─── SCRAPER ────────────────────────────────────────

def scrape():
    prodotti = []

    for nome_sito, URL in URLS.items():
        r = requests.get(URL, headers=HEADERS)
        soup = BeautifulSoup(r.text, "html.parser")

        for c in soup.select("li.product"):
            try:
                nome = c.select_one(".woocommerce-loop-product__title").text.strip()
                prezzo_raw = c.select_one(".price").text.strip()
                link = c.select_one("a")["href"]
                disponibile = not c.select_one(".out-of-stock")

                prodotti.append({
                    "nome": nome,
                    "prezzo": prezzo_raw,
                    "disponibile": disponibile,
                    "link": link,
                    "sito": nome_sito
                })
            except:
                pass

    return prodotti

# ─── CONFRONTO TRA SITI ─────────────────────────────

def confronta_siti(prodotti):
    mappa = {}

    for p in prodotti:
        nome = p["nome"]
        prezzo = estrai_prezzo(p["prezzo"])

        if prezzo is None:
            continue

        if nome not in mappa:
            mappa[nome] = []

        mappa[nome].append({
            "prezzo": prezzo,
            "sito": p["sito"],
            "link": p["link"]
        })

    for nome, lista in mappa.items():
        if len(lista) < 2:
            continue

        lista.sort(key=lambda x: x["prezzo"])
        migliore = lista[0]
        peggiore = lista[-1]

        diff = peggiore["prezzo"] - migliore["prezzo"]

        if diff > 0:
            testo = f"⚖️ *CONFRONTO PREZZI*\n\n"
            testo += f"📦 {nome}\n\n"
            testo += f"🏆 Migliore: {migliore['prezzo']}€ ({migliore['sito']})\n"
            testo += f"💸 Peggiore: {peggiore['prezzo']}€ ({peggiore['sito']})\n"
            testo += f"📉 Risparmi: {diff:.2f}€"

            invia_telegram(testo, migliore["link"])

def estrai_prezzo(p):
    try:
        return float(p.replace("€", "").replace(",", ".").strip())
    except:
        return None

# ─── GIST ───────────────────────────────────────────

def carica_stato():
    r = requests.get(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GIST_TOKEN}"}
    )
    if r.ok:
        return json.loads(r.json()["files"][GIST_FILE]["content"])
    return {}

def salva_stato(prodotti, vecchi):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    nuovo = {}

    for p in prodotti:
        nome = p["nome"]
        storico = vecchi.get(nome, {}).get("storico", [])

        storico.append({"prezzo": p["prezzo"], "data": now})
        storico = storico[-50:]

        nuovo[nome] = {
            "prezzo": p["prezzo"],
            "disponibile": p["disponibile"],
            "link": p["link"],
            "storico": storico
        }

    requests.patch(
        f"https://api.github.com/gists/{GIST_ID}",
        headers={"Authorization": f"token {GIST_TOKEN}"},
        json={"files": {GIST_FILE: {"content": json.dumps(nuovo, indent=2)}}}
    )

# ─── MAIN ───────────────────────────────────────────

def main():
    prodotti = scrape()
    vecchi = carica_stato()

    if not vecchi:
        salva_stato(prodotti, {})
        invia_telegram("✅ Monitor attivo!")
        return

    confronta_siti(prodotti)  # 🔥 QUI IL CONFRONTO

    salva_stato(prodotti, vecchi)

if __name__ == "__main__":
    main()
