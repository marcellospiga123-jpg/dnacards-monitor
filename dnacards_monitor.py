"""
DNA Cards - Monitor prezzi e disponibilità
Versione GitHub Actions — gira una volta sola, stato salvato su GitHub Gist
"""

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ─── CONFIGURAZIONE ───────────────────────────────────────────────────────────

URL = "https://dnacards.it/categoria/one-piece/display-buste-one-piece-en/"

EMAIL_ATTIVA       = True
EMAIL_MITTENTE     = os.environ.get("EMAIL_MITTENTE", "")
EMAIL_PASSWORD     = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_DESTINATARIO = os.environ.get("EMAIL_DESTINATARIO", "")
EMAIL_SMTP         = "smtp.gmail.com"
EMAIL_PORT         = 587

GIST_TOKEN = os.environ.get("GIST_TOKEN", "")
GIST_ID    = os.environ.get("GIST_ID", "")
GIST_FILE  = "dnacards_stato.json"

# ─── STATO SU GIST ───────────────────────────────────────────────────────────

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
        print(f"  [!] Errore caricamento stato: {e}")
    return {}

def salva_stato(prodotti):
    if not GIST_ID or not GIST_TOKEN:
        return
    stato = {p["nome"]: {"prezzo": p["prezzo"], "disponibile": p["disponibile"]} for p in prodotti}
    try:
        requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"token {GIST_TOKEN}"},
            json={"files": {GIST_FILE: {"content": json.dumps(stato, ensure_ascii=False, indent=2)}}},
            timeout=10,
        )
        print("  Stato salvato su Gist.")
    except Exception as e:
        print(f"  [!] Errore salvataggio stato: {e}")

# ─── SCRAPING ────────────────────────────────────────────────────────────────
def scrape_prodotti():
    prodotti = []

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.get(URL, headers=headers, timeout=20)
    html = r.text

    # Split veloce sui prodotti
    blocchi = html.split('class="product"')

    print(f"  Trovati {len(blocchi)-1} prodotti nella pagina.")

    for blocco in blocchi[1:]:
        try:
            # Nome
            nome = "N/D"
            if 'woocommerce-loop-product__title' in blocco:
                nome = blocco.split('woocommerce-loop-product__title">')[1].split("<")[0].strip()

            # Prezzo
            prezzo = None
            if 'amount">' in blocco:
                prezzo = blocco.split('amount">')[1].split("<")[0].strip()

            # Disponibilità
            in_stock = True
            if "out-of-stock" in blocco or "disabled" in blocco:
                in_stock = False

            # Link
            link = URL
            if 'href="' in blocco:
                link = blocco.split('href="')[1].split('"')[0]

            prodotti.append({
                "nome": nome,
                "prezzo": prezzo,
                "disponibile": in_stock,
                "link": link,
            })

        except Exception as e:
            print(f"  [!] Errore parsing prodotto: {e}")

    return prodotti


# ─── CONFRONTO ───────────────────────────────────────────────────────────────

def confronta(prodotti_nuovi, stato_vecchio):
    variazioni = []
    for p in prodotti_nuovi:
        nome = p["nome"]
        vecchio = stato_vecchio.get(nome)

        if vecchio is None:
            variazioni.append({
                "tipo": "nuovo",
                "nome": nome,
                "prezzo": p["prezzo"],
                "disponibile": p["disponibile"],
                "link": p["link"],
            })
            continue

        if vecchio["prezzo"] != p["prezzo"]:
            variazioni.append({
                "tipo": "prezzo",
                "nome": nome,
                "prezzo_vecchio": vecchio["prezzo"],
                "prezzo_nuovo": p["prezzo"],
                "disponibile": p["disponibile"],
                "link": p["link"],
            })

        if vecchio["disponibile"] != p["disponibile"]:
            tipo = "tornato_disponibile" if p["disponibile"] else "esaurito"
            variazioni.append({
                "tipo": tipo,
                "nome": nome,
                "prezzo": p["prezzo"],
                "link": p["link"],
            })

    return variazioni

# ─── NOTIFICHE ───────────────────────────────────────────────────────────────

def formatta_messaggio(variazioni):
    righe = [f"🔔 DNA Cards — {len(variazioni)} variazione/i rilevata/e\n"]
    for v in variazioni:
        if v["tipo"] == "prezzo":
            righe.append(
                f"💰 PREZZO CAMBIATO: {v['nome']}\n"
                f"   {v['prezzo_vecchio']} → {v['prezzo_nuovo']}\n"
                f"   {v['link']}"
            )
        elif v["tipo"] == "esaurito":
            righe.append(
                f"❌ ESAURITO: {v['nome']}\n"
                f"   Prezzo: {v.get('prezzo', 'N/D')}\n"
                f"   {v['link']}"
            )
        elif v["tipo"] == "tornato_disponibile":
            righe.append(
                f"✅ TORNATO DISPONIBILE: {v['nome']}\n"
                f"   Prezzo: {v.get('prezzo', 'N/D')}\n"
                f"   {v['link']}"
            )
        elif v["tipo"] == "nuovo":
            stato = "Disponibile" if v["disponibile"] else "Esaurito"
            righe.append(
                f"🆕 NUOVO PRODOTTO: {v['nome']}\n"
                f"   Prezzo: {v.get('prezzo', 'N/D')} — {stato}\n"
                f"   {v['link']}"
            )
    return "\n\n".join(righe)

def invia_email(testo):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "DNA Cards — Variazione prezzo/disponibilità"
        msg["From"] = EMAIL_MITTENTE
        msg["To"] = EMAIL_DESTINATARIO
        msg.attach(MIMEText(testo, "plain", "utf-8"))
        with smtplib.SMTP(EMAIL_SMTP, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_MITTENTE, EMAIL_PASSWORD)
            server.sendmail(EMAIL_MITTENTE, EMAIL_DESTINATARIO, msg.as_string())
        print("  ✉️  Email inviata.")
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
    print("🤖 DNA Cards Monitor — controllo in corso...")
    print(f"   URL: {URL}\n")

    try:
        prodotti = scrape_prodotti()

        if not prodotti:
            print("  [!] Nessun prodotto trovato, possibile errore di caricamento pagina.")
            return

        stato_vecchio = carica_stato()

        if not stato_vecchio:
            print("  Primo avvio: salvo stato iniziale. Le notifiche partiranno dal prossimo controllo.")
            salva_stato(prodotti)
        else:
            variazioni = confronta(prodotti, stato_vecchio)
            if variazioni:
                print(f"  ⚠️  {len(variazioni)} variazione/i rilevata/e!")
                invia_notifiche(variazioni)
                salva_stato(prodotti)
            else:
                print("  Nessuna variazione rilevata.")

    except Exception as e:
        print(f"  [ERRORE] {e}")
        raise


if __name__ == "__main__":
    main()
