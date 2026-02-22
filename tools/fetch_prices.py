#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ivo's Flighttracker — QuickStart fetcher
----------------------------------------
Deze versie is geoptimaliseerd om *snel* een eerste dataset te vullen,
zodat je grafieken zichtbaar worden. Daarna kun je 'm eenvoudig uitbreiden.

Wat doet dit script:
- Leest AMADEUS_API_KEY / AMADEUS_API_SECRET uit GitHub Secrets
- Haalt voor een *kleine set routes en datums* actuele prijzen op
- Schrijft:
  - data/sample_data.json          (tijdreeks voor 'beste aankoopmoment')
  - data/monthly_lowest.json       (laagste prijs per week-bucket in jul/aug voor 2026 en 2025)
- Print duidelijke logs naar GitHub Actions (zodat je issues snel ziet)

Na je eerste succesvolle run:
- Zet QUICKSTART = False
- Zet ROUTES_ALL aan (alle routes)
- (optioneel) maak het kalenderbereik groter (hele jaar)

Auteur: jouw Copilot, feb 2026
"""

import os
import json
import time
import sys
import datetime as dt
from typing import Dict, List, Tuple

import requests

# ===========================
# 🔧 Instellingen
# ===========================

# QuickStart aan/uit. Zet op False als alles werkt en je volle dataset wilt.
QUICKSTART = True

# Routes (volledige set voor later gebruik)
ROUTES_ALL = [
    ("AMS", "LIS"), ("AMS", "OPO"), ("AMS", "BKK"), ("AMS", "ZAG"), ("AMS", "SPU"),
    ("EIN", "LIS"), ("EIN", "OPO"), ("EIN", "BKK"), ("EIN", "ZAG"), ("EIN", "SPU"),
]

# QuickStart: kleine subset (snel resultaat)
ROUTES_QS = [
    ("AMS", "LIS"),
    ("AMS", "OPO"),
]

ROUTES = ROUTES_QS if QUICKSTART else ROUTES_ALL

# QuickStart: slechts 3 vertrekdagen in jouw venster (snel)
QS_START_DATES = ["2026-07-20", "2026-07-25", "2026-08-01"]

# Reisperiode/delta's
TRIP_LEN = 21
TRIP_FLEX = 1 if QUICKSTART else 2  # ±1 voor sneller bij QuickStart

# Kalenderjaren (nu en referentie)
YEAR_NOW = 2026
YEAR_PREV = 2025

# Bestanden
DATA_DIR = "data"
SAMPLE_PATH = os.path.join(DATA_DIR, "sample_data.json")
MONTHLY_PATH = os.path.join(DATA_DIR, "monthly_lowest.json")

# Amadeus API
AMADEUS_BASE = "https://test.api.amadeus.com"  # 'test' omgeving volstaat voor dit doel
TIMEOUT = 30
RETRY = 3


# ===========================
# 🔎 Hulpfuncties
# ===========================

def log(msg: str) -> None:
    """Netjes loggen naar Actions-uitvoer."""
    print(f"[fetch] {msg}", flush=True)


def require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        log(f"ERROR: Missing environment variable: {name}")
        sys.exit(1)
    return val


def amadeus_token(client_id: str, client_secret: str) -> str:
    url = f"{AMADEUS_BASE}/v1/security/oauth2/token"
    data = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    for i in range(RETRY):
        try:
            r = requests.post(url, data=data, timeout=TIMEOUT)
            if r.status_code == 200:
                tok = r.json().get("access_token")
                if tok:
                    log("Got Amadeus access token.")
                    return tok
            log(f"Token attempt {i+1} failed: {r.status_code} {r.text[:300]}")
        except Exception as e:
            log(f"Token attempt {i+1} exception: {e}")
        time.sleep(1 + i)
    log("ERROR: Could not obtain Amadeus token after retries.")
    sys.exit(1)


def offers_search(tok: str, origin: str, dest: str, dep: str, ret: str, max_results: int = 10) -> List[dict]:
    """Flight Offers Search (basic) — returns list of offers (can be empty)."""
    url = f"{AMADEUS_BASE}/v2/shopping/flight-offers"
    params = {
        "originLocationCode": origin,
        "destinationLocationCode": dest,
        "departureDate": dep,
        "returnDate": ret,
        "adults": 2,
        "currencyCode": "EUR",
        "max": max_results,
    }
    headers = {"Authorization": f"Bearer {tok}"}
    for i in range(RETRY):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json().get("data", []) or []
            if r.status_code in (429, 500, 502, 503, 504):
                log(f"Offers retry {i+1}: {r.status_code} {r.text[:120]}")
                time.sleep(1 + i)
                continue
            log(f"Offers ERROR {r.status_code}: {r.text[:300]}")
            return []
        except Exception as e:
            log(f"Offers exception (try {i+1}): {e}")
            time.sleep(1 + i)
    return []


def ensure_file(path: str, default):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False)


def update_time_series(sample_path: str, snapshots: List[dict]) -> None:
    ensure_file(sample_path, [])
    try:
        with open(sample_path, "r", encoding="utf-8") as f:
            cur = json.load(f)
    except Exception:
        cur = []
    cur.extend(snapshots)

    # Houd bestand compact
    if len(cur) > 60000:
        cur = cur[-60000:]

    with open(sample_path, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False)
    log(f"Wrote {len(snapshots)} rows to {sample_path} (total ~{len(cur)}).")


def update_monthly_buckets(path: str, route_key: str, year: int, cal: Dict[str, float]) -> None:
    """
    cal: dict YYYY-MM-DD -> price
    We nemen per maand 4 week-buckets (W1..W4) en kiezen de minimumprijs per bucket.
    """
    ensure_file(path, {})
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception:
        obj = {}

    obj.setdefault(route_key, {}).setdefault(str(year), {})

    buckets: Dict[str, List] = {}  # "07" -> [minW1, minW2, minW3, minW4]
    for d, price in cal.items():
        y, m, day = d.split("-")
        if int(y) != year:
            continue
        b = min((int(day) - 1) // 7, 3)  # 0..3
        arr = buckets.setdefault(m, [None, None, None, None])
        cur = arr[b]
        arr[b] = min(price, cur) if (cur is not None) else price

    for m, arr in buckets.items():
        obj[route_key][str(year)][m] = arr

    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    log(f"Updated monthly buckets for {route_key} / {year}: months={sorted(list(buckets.keys()))}")


def calendar_cheapest(tok: str, origin: str, dest: str, year: int) -> Dict[str, float]:
    """
    QuickStart-variant:
    - Alleen juli/augustus van 'year'
    - Om de dag (i.p.v. elke dag)
    - Kleinere sleep voor snelheid
    """
    start = dt.date(year, 7, 1)
    end = dt.date(year, 8, 31)
    d = start
    cal: Dict[str, float] = {}
    while d <= end:
        dep = d.isoformat()
        ret = (d + dt.timedelta(days=TRIP_LEN)).isoformat()
        data = offers_search(tok, origin, dest, dep, ret, max_results=8)
        if data:
            best = min(float(o["price"]["total"]) for o in data)
            cal[dep] = best
        d += dt.timedelta(days=2)
        time.sleep(0.15)
    return cal


def extract_best_row(offer: dict, origin: str, dest: str, dep: dt.date, ret: dt.date, fetched_at: str, today: dt.date) -> dict:
    """Maak een nette rij voor sample_data.json."""
    price = float(offer["price"]["total"])
    try:
        segs = offer["itineraries"][0]["segments"]
        stops = len(segs) - 1
        carrier = segs[0]["carrierCode"]
        lay = 0.0
        for i in range(len(segs) - 1):
            a = dt.datetime.fromisoformat(segs[i]["arrival"]["at"].replace("Z", "+00:00"))
            b = dt.datetime.fromisoformat(segs[i + 1]["departure"]["at"].replace("Z", "+00:00"))
            lay += (b - a).total_seconds() / 3600.0
        lay = round(lay, 1)
    except Exception:
        carrier, stops, lay = "N/A", 1, 2.0

    return {
        "country": "AUTO",
        "origin": origin,
        "destination_iata": dest,
        "outbound_date": dep.isoformat(),
        "return_date": ret.isoformat(),
        "trip_length_days": (ret - dep).days,
        "days_before_departure": (dep - today).days,
        "price_eur": int(price),
        "airline": carrier,
        "stops": stops,
        "max_layover_hours": lay,
        "fetched_at": fetched_at,
    }


# ===========================
# 🚀 Main
# ===========================

def main():
    # 1) Secrets
    key = require_env("AMADEUS_API_KEY")
    secret = require_env("AMADEUS_API_SECRET")

    # 2) Token
    tok = amadeus_token(key, secret)

    # 3) Timestamps/paths
    today = dt.date.today()
    fetched_at = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(DATA_DIR, exist_ok=True)

    all_rows: List[dict] = []

    # 4) Tijdreeks (klein en snel in QuickStart)
    for (orig, dst) in ROUTES:
        log(f"=== Route {orig}-{dst} ===")
        count_added = 0

        # QuickStart: slechts enkele vertrekdagen ± TRIP_FLEX
        dep_dates = [dt.date.fromisoformat(d) for d in (QS_START_DATES if QUICKSTART else QS_START_DATES)]
        # (Je kunt hier voor 'vol' een echte window-loop toevoegen i.p.v. QS_START_DATES)

        for dep in dep_dates:
            for flex in range(-TRIP_FLEX, TRIP_FLEX + 1):
                ret = dep + dt.timedelta(days=TRIP_LEN + flex)
                data = offers_search(tok, orig, dst, dep.isoformat(), ret.isoformat(), max_results=8)
                if not data:
                    continue
                best_offer = min(data, key=lambda o: float(o["price"]["total"]))
                row = extract_best_row(best_offer, orig, dst, dep, ret, fetched_at, today)
                all_rows.append(row)
                count_added += 1
                log(f"Added: {orig}-{dst} {dep}→{ret} €{row['price_eur']} stops:{row['stops']}")

        # 5) Kalender voor maandgrafiek (jul/aug 2026 & 2025)
        for yy in (YEAR_NOW, YEAR_PREV):
            cal = calendar_cheapest(tok, orig, dst, yy)
            update_monthly_buckets(MONTHLY_PATH, f"{orig}-{dst}", yy, cal)

        log(f"Route {orig}-{dst}: added {count_added} time-series rows.")

    # 6) Schrijf tijdreeks
    update_time_series(SAMPLE_PATH, all_rows)

    # 7) Samenvatting
    log("QuickStart fetch complete.")
    log(f"- sample_data.json size: {os.path.getsize(SAMPLE_PATH)} bytes")
    log(f"- monthly_lowest.json size: {os.path.getsize(MONTHLY_PATH)} bytes")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)
