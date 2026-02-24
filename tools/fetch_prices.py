# tools/fetch_prices.py
import os
import json
import time
import math
import pathlib
import datetime as dt
from typing import Dict, Any, List, Tuple
import requests

TEQUILA_BASE = "https://tequila-api.kiwi.com"
SEARCH_ENDPOINT = f"{TEQUILA_BASE}/v2/search"

def dmy(date: dt.date) -> str:
    # Tequila expects DD/MM/YYYY
    return date.strftime("%d/%m/%Y")

def iso(date: dt.date) -> str:
    return date.isoformat()

def env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if (v is not None and v != "") else default

def fetch_lowest_for_day(api_key: str, src: str, dst: str, day: dt.date, currency: str) -> Dict[str, Any]:
    """
    Query Tequila for a single day, return the cheapest option (if any).
    """
    headers = {"apikey": api_key}
    params = {
        "fly_from": src,
        "fly_to": dst,
        "date_from": dmy(day),
        "date_to": dmy(day),
        "flight_type": "oneway",
        "adults": 1,
        "curr": currency,
        "limit": 50,
        "sort": "price",
        "one_for_city": 1,
    }

    r = requests.get(SEARCH_ENDPOINT, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    items = data.get("data", []) or []
    if not items:
        return {}

    best = items[0]  # sorted by price asc (limit 50)
    out = {
        "date": iso(day),
        "price": best.get("price"),
        "currency": currency,
        "fly_from": best.get("flyFrom"),
        "fly_to": best.get("flyTo"),
        "city_from": best.get("cityFrom"),
        "city_to": best.get("cityTo"),
        "airlines": best.get("airlines"),
        "local_departure": best.get("local_departure"),
        "deep_link": best.get("deep_link"),
    }
    return out

def ensure_dirs():
    pathlib.Path("data").mkdir(parents=True, exist_ok=True)
    pathlib.Path("tools").mkdir(parents=True, exist_ok=True)

def parse_routes(routes_env: str) -> List[Tuple[str, str]]:
    routes: List[Tuple[str, str]] = []
    if not routes_env:
        return routes
    for chunk in routes_env.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            continue
        a, b = chunk.split(":", 1)
        routes.append((a.strip().upper(), b.strip().upper()))
    return routes

def main():
    ensure_dirs()

    api_key = os.environ.get("KIWI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("KIWI_API_KEY is not set (repo secret).")

    routes_env = env("ROUTES", "AMS:BCN")  # QuickStart: klein houden
    days_ahead = int(env("DAYS_AHEAD", "14"))
    currency = env("CURRENCY", "EUR")

    routes = parse_routes(routes_env)
    if not routes:
        raise SystemExit("No routes provided (ROUTES env is empty).")

    today = dt.date.today()
    horizon = [today + dt.timedelta(days=i) for i in range(0, max(1, days_ahead))]

    # sample_data accumuleert een “snelle” weergave
    sample_payload: Dict[str, Any] = {
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "currency": currency,
        "routes": []
    }

    # monthly_lowest: per route -> per dag (huidige maand) de goedkoopste prijs
    current_month_start = today.replace(day=1)
    next_month = (current_month_start + dt.timedelta(days=32)).replace(day=1)
    current_month_days = []
    d = current_month_start
    while d < next_month:
        current_month_days.append(d)
        d += dt.timedelta(days=1)

    monthly_lowest: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for (src, dst) in routes:
        route_key = f"{src}-{dst}"

        # QuickStart: loop alleen over horizon (klein en snel)
        per_day = []
        for day in horizon:
            try:
                rec = fetch_lowest_for_day(api_key, src, dst, day, currency)
            except requests.HTTPError as e:
                # Geef lucht aan rate-limits / 4xx/5xx, maar niet hard falen
                rec = {}
                print(f"[WARN] {src}->{dst} {day}: HTTP {getattr(e.response, 'status_code', '?')} {e}")
            except Exception as e:
                rec = {}
                print(f"[WARN] {src}->{dst} {day}: {e}")

            if rec:
                per_day.append(rec)
            time.sleep(0.2)  # kleine pauze om burst te verlagen

        # sample_data.json
        sample_payload["routes"].append({
            "fly_from": src,
            "fly_to": dst,
            "days": per_day,
        })

        # monthly_lowest.json (alleen huidige maand — compatibel en klein)
        # NB: ook als horizon < maandlengte kan zijn; we vullen wat we hebben
        day_min: Dict[str, Any] = {}
        for day in current_month_days:
            # zoek entry voor deze dag
            dstr = iso(day)
            candidates = [x for x in per_day if x.get("date") == dstr]
            if candidates:
                best = min(candidates, key=lambda x: (x.get("price") or 10**9))
                day_min[dstr] = {
                    "price": best.get("price"),
                    "currency": currency
                }
        monthly_lowest[route_key] = day_min

    # Schrijf bestanden
    with open("data/sample_data.json", "w", encoding="utf-8") as f:
        json.dump(sample_payload, f, ensure_ascii=False, indent=2)

    with open("data/monthly_lowest.json", "w", encoding="utf-8") as f:
        json.dump(monthly_lowest, f, ensure_ascii=False, indent=2)

    print("Wrote data/sample_data.json and data/monthly_lowest.json")

if __name__ == "__main__":
    main()
