#!/usr/bin/env python3
"""
Vigila el estado del cupo de la visa Work and Holiday (subclass 462) para un país
y envía una notificación push al celular (vía ntfy.sh) apenas cambia.

Cómo se asegura de leer la versión más reciente de la página:
  1. La abre con un navegador real (Chromium, vía Playwright), igual que una persona,
     sin caché y con un parámetro distinto en cada consulta.
  2. También la descarga de forma directa, como segunda fuente.
  3. Lee la fecha de "Last updated" de cada copia y se queda con la más nueva.
  4. Si la copia más nueva es MÁS VIEJA que la última que ya vio, la descarta
     (no cambia el estado) y lo reintenta en el próximo chequeo.

Variables de entorno:
  NTFY_TOPIC         (obligatoria) nombre del canal de ntfy al que estás suscripto en el celular
  COUNTRY            país a vigilar (por defecto: Argentina)
  NTFY_SERVER        servidor de ntfy (por defecto: https://ntfy.sh)
  STATE_FILE         archivo donde se guarda el último estado (por defecto: state.json)
  REMIND_WHILE_OPEN  "1" = seguir avisando en cada chequeo mientras esté abierta (por defecto: 1)
  FORCE_TEST         "1" = enviar una notificación de prueba con el estado y la versión leída
  PAGE_URL           solo para pruebas: otra URL o archivo local en lugar de la página real
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

URL = os.environ.get("PAGE_URL",
                     "https://immi.homeaffairs.gov.au/what-we-do/whm-program/status-of-country-caps")
APPLY_URL = ("https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/"
             "work-holiday-462/first-work-holiday-462")

COUNTRY = os.environ.get("COUNTRY", "Argentina")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
REMIND_WHILE_OPEN = os.environ.get("REMIND_WHILE_OPEN", "1") == "1"
FORCE_TEST = os.environ.get("FORCE_TEST") == "1"
HEARTBEAT_DAYS = 7  # cada cuántos días mandar un "sigo vigilando" (aparte de los avisos de cambio)

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# La página de Home Affairs mete muchos caracteres invisibles dentro de las celdas.
INVISIBLE = re.compile("[​‌‍⁠﻿ ]")

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", INVISIBLE.sub(" ", text)).strip()


# ----------------------------------------------------------------------------- lectura

class TableParser(HTMLParser):
    """Junta todas las filas de todas las tablas como listas de textos de celda."""

    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(clean(" ".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def classify(raw: str) -> str:
    s = raw.lower()
    if "ballot" in s:
        return "ballot"
    for status in ("open", "paused", "closed"):
        if status in s:
            return status
    return raw or "desconocido"


def get_status(html: str) -> tuple[str, str]:
    parser = TableParser()
    parser.feed(html)
    for row in parser.rows:
        if len(row) >= 2 and row[0].lower() == COUNTRY.lower():
            return classify(row[1]), row[1]
    raise RuntimeError(f"No encontré la fila de '{COUNTRY}' en la tabla")


def get_last_updated(html: str) -> tuple[str, datetime | None]:
    """Texto de 'Last updated' y su fecha. Entiende '28/09/2026 3:47 PM' y '29 September 2026'."""
    text = clean(re.sub(r"<[^>]+>", " ", html))
    m = re.search(r"Last updated:?\s*(\d{1,2})[/ ]([A-Za-z]+|\d{1,2})[/ ](\d{4})"
                  r"(?:\s+(\d{1,2}):(\d{2})\s*([AP]M))?", text, re.IGNORECASE)
    if not m:
        return "desconocida", None
    day, month, year, hh, mm, ampm = m.groups()
    month_n = int(month) if month.isdigit() else MONTHS.get(month.lower())
    if not month_n:
        return m.group(0), None
    hour, minute = 0, 0
    if hh:
        hour, minute = int(hh) % 12 + (12 if ampm.upper() == "PM" else 0), int(mm)
    try:
        dt = datetime(int(year), month_n, int(day), hour, minute)
    except ValueError:
        return m.group(0), None
    return m.group(0).replace("Last updated", "").strip(" :"), dt


# ----------------------------------------------------------------------------- descarga

def busted_url() -> str:
    if not URL.startswith("http"):
        return URL
    return f"{URL}{'&' if '?' in URL else '?'}t={int(time.time() * 1000)}"


def fetch_with_browser() -> str:
    """Abre la página con Chromium real, sin caché, y espera a que la tabla esté cargada."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(user_agent=USER_AGENT, locale="en-AU",
                                      extra_http_headers={"Cache-Control": "no-cache",
                                                          "Pragma": "no-cache"})
        page = context.new_page()
        # Desactiva la caché del navegador para esta pestaña.
        cdp = context.new_cdp_session(page)
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        page.goto(busted_url(), wait_until="networkidle", timeout=90_000)
        try:
            page.wait_for_selector(f"td:has-text('{COUNTRY}')", timeout=30_000)
        except Exception:  # noqa: BLE001 - igual devolvemos lo que haya para diagnosticar
            pass
        html = page.content()
        browser.close()
        return html


def fetch_direct() -> str:
    if not URL.startswith("http"):
        with open(URL.removeprefix("file://"), encoding="utf-8") as f:
            return f.read()
    req = urllib.request.Request(busted_url(), headers={
        "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-AU,en;q=0.9", "Cache-Control": "no-cache", "Pragma": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", errors="replace")


def read_page() -> dict:
    """Lee la página por todas las vías disponibles y devuelve la lectura con la fecha más nueva."""
    readings, errors = [], []
    for name, fetch in (("navegador", fetch_with_browser), ("directa", fetch_direct)):
        for attempt in range(2):
            try:
                html = fetch()
                status, raw = get_status(html)
                updated_text, updated_dt = get_last_updated(html)
                readings.append({"via": name, "status": status, "raw": raw,
                                 "updated_text": updated_text, "updated_dt": updated_dt})
                print(f"[{name}] {COUNTRY}: {status} ({raw!r}) | Last updated: {updated_text}")
                break
            except Exception as err:  # noqa: BLE001
                errors.append(f"{name}: {err}")
                print(f"[{name}] intento {attempt + 1} falló: {err}", file=sys.stderr)
                time.sleep(5)
    if not readings:
        raise RuntimeError("No pude leer la página (" + " | ".join(errors[-2:]) + ")")
    # La más nueva primero; si empatan, preferimos la del navegador (orden de inserción).
    readings.sort(key=lambda r: (r["updated_dt"] or datetime.min).date(), reverse=True)
    best = readings[0]
    best["all"] = readings
    return best


# ----------------------------------------------------------------------------- avisos y estado

def notify(title: str, message: str, priority: int = 3, tags=None, click: str | None = None):
    if not NTFY_TOPIC:
        print(f"[sin NTFY_TOPIC] {title}: {message}")
        return
    payload = {"topic": NTFY_TOPIC, "title": title, "message": message,
               "priority": priority, "tags": tags or []}
    if click:
        payload["click"] = click
        payload["actions"] = [{"action": "view", "label": "Abrir página", "url": click}]
    req = urllib.request.Request(NTFY_SERVER, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()
    print(f"Notificación enviada: {title}")


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main() -> int:
    state = load_state()
    now = datetime.now(timezone.utc)

    try:
        r = read_page()
    except Exception as err:  # noqa: BLE001
        print(f"ERROR: {err}", file=sys.stderr)
        if not state.get("error_notified"):
            notify("⚠️ Bot visa 462: error", f"{err}. Revisá la página a mano mientras tanto.",
                   priority=3, tags=["warning"], click=URL)
            state["error_notified"] = True
            save_state(state)
        return 1

    status, updated_text, updated_dt = r["status"], r["updated_text"], r["updated_dt"]
    state["error_notified"] = False
    versions = ", ".join(f"{x['via']}: {x['updated_text']}" for x in r["all"])

    # Protección contra copias viejas: nunca retroceder a una versión anterior a la ya vista.
    seen_text = state.get("page_last_updated")
    seen_dt = datetime.fromisoformat(state["page_last_updated_iso"]) \
        if state.get("page_last_updated_iso") else None
    # Se compara solo el día: una versión muestra la hora y la otra no.
    stale = bool(updated_dt and seen_dt and updated_dt.date() < seen_dt.date())

    if FORCE_TEST:
        notify("🧪 Prueba bot visa 462",
               f"Funciona. Estado de {COUNTRY}: {status.upper()}\n"
               f"Versión leída: Last updated {updated_text}\n({versions})"
               + ("\n⚠️ Es MÁS VIEJA que una ya vista; se ignora." if stale else ""),
               priority=3, tags=["test_tube"], click=URL)

    if stale:
        print(f"Copia vieja ({updated_text}) anterior a la ya vista ({seen_text}); se ignora.")
        save_state(state)
        return 0

    if updated_dt:
        state["page_last_updated"] = updated_text
        state["page_last_updated_iso"] = updated_dt.isoformat()

    previous = state.get("status")

    if status == "open" and (previous != "open" or REMIND_WHILE_OPEN):
        notify(f"🇦🇺 ¡ABRIÓ la visa 462 para {COUNTRY}!",
               f"El cupo está OPEN (página: Last updated {updated_text}). "
               "Entrá a ImmiAccount y aplicá ya.",
               priority=5, tags=["rotating_light", "kangaroo"], click=APPLY_URL)
    elif previous is None:
        notify("✅ Bot visa 462 activo",
               f"Empecé a vigilar cada 15 min. Estado de {COUNTRY}: {status.upper()} "
               f"(Last updated {updated_text})", priority=2, tags=["eyes"], click=URL)
    elif status != previous:
        notify(f"Visa 462 {COUNTRY}: {previous.upper()} → {status.upper()}",
               f"Cambió el estado del cupo (Last updated {updated_text}).",
               priority=4, tags=["bell"], click=URL)

    if status != previous:
        state["status"] = status
        state["changed_at"] = now.isoformat(timespec="seconds")

    # Aviso semanal de que el bot sigue vivo (independiente de los avisos de cambio, que son
    # inmediatos). También genera un commit que evita que GitHub apague el workflow.
    last_hb = state.get("heartbeat_at")
    if not last_hb or (now - datetime.fromisoformat(last_hb)).days >= HEARTBEAT_DAYS:
        if last_hb:
            notify("Bot visa 462: sigo vigilando",
                   f"Estado de {COUNTRY}: {status.upper()} (Last updated {updated_text})",
                   priority=1, tags=["eyes"])
        state["heartbeat_at"] = now.isoformat(timespec="seconds")

    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
