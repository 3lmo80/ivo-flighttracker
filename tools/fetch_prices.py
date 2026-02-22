#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automatische prijsfetcher voor Ivo's Flighttracker (2×/dag).
- Vult/actualiseert: data/sample_data.json (tijdreeks)
- Vult/actualiseert: data/monthly_lowest.json (laagste prijs per maand in week-buckets) voor 2026 én 2025

Benodigd in GitHub Actions Secrets:
- AMADEUS_API_KEY
- AMADEUS_API_SECRET

NB: Dit voorbeeld gebruikt Amadeus Flight Offers als basis. In productie
kunnen we dit optimaliseren met Amadeus 'Cheapest Date Search' en 'Price Analysis'.
"""
import os, json, time, datetime as dt
import requests

API_KEY = os.environ["AMADEUS_API_KEY"]
API_SECRET = os.environ["AMADEUS_API_SECRET"]

ROUTES = [
    ("AMS","LIS"),("AMS","OPO"),("AMS","BKK"),("AMS","ZAG"),("AMS","SPU"),
    ("EIN","LIS"),("EIN","OPO"),("EIN","BKK"),("EIN","ZAG"),("EIN","SPU"),
]
YEAR_NOW, YEAR_PREV = 2026, 2025
TRIP_LEN, TRIP_FLEX = 21, 2

BASE = "https://test.api.amadeus.com"

def token():
    r = requests.post(f"{BASE}/v1/security/oauth2/token", data={
        "grant_type":"client_credentials","client_id":API_KEY,"client_secret":API_SECRET
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

def search(tok, origin, dest, dep, ret):
    r = requests.get(f"{BASE}/v2/shopping/flight-offers", headers={"Authorization":f"Bearer {tok}"}, params={
        "originLocationCode":origin,"destinationLocationCode":dest,
        "departureDate":dep,"returnDate":ret,"adults":2,"currencyCode":"EUR","max":10
    }, timeout=30)
    r.raise_for_status(); return r.json().get("data", [])


def update_time_series(sample_path, rows):
    try:
        with open(sample_path, "r", encoding="utf-8") as f:
            cur = json.load(f)
    except Exception:
        cur = []
    cur.extend(rows)
    # houd bestand compact
    if len(cur) > 60000:
        cur = cur[-60000:]
    with open(sample_path, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False)


def update_monthly_buckets(path, route_key, year, cal):
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception:
        obj = {}
    obj.setdefault(route_key, {}).setdefault(str(year), {})
    buckets = {}
    for d, price in cal.items():
        y, m, day = d.split("-")
        if int(y) != year: continue
        b = min((int(day)-1)//7, 3)
        buckets.setdefault(m, [None,None,None,None])
        cur = buckets[m][b]
        buckets[m][b] = min(price, cur) if cur is not None else price
    for m, arr in buckets.items():
        obj[route_key][str(year)][m] = arr
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def calendar_cheapest(tok, origin, dest, year):
    # Simpele, conservatieve kalender: we lopen dagen door in batches
    # (kan worden vervangen door Amadeus Cheapest Date/Calendar endpoint)
    start = dt.date(year,1,1); end = dt.date(year,12,31)
    d = start; cal = {}
    while d <= end:
        dep = d.isoformat()
        ret = (d + dt.timedelta(days=TRIP_LEN)).isoformat()
        try:
            data = search(tok, origin, dest, dep, ret)
            if data:
                best = min(float(o["price"]["total"]) for o in data)
                cal[dep] = best
        except Exception:
            pass
        d += dt.timedelta(days=1)
        time.sleep(0.2)
    return cal


def main():
    tok = token()
    today = dt.date.today()
    fetched = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    sample_path = os.path.join("data","sample_data.json")
    monthly_path = os.path.join("data","monthly_lowest.json")

    rows = []
    for (orig, dst) in ROUTES:
        # zomerwindow
        start = dt.date(2026,7,18); end = dt.date(2026,8,26)
        cur = start
        while cur <= end:
            dep = cur.isoformat()
            for flex in range(-TRIP_FLEX, TRIP_FLEX+1):
                ret = (cur + dt.timedelta(days=TRIP_LEN+flex)).isoformat()
                try:
                    data = search(tok, orig, dst, dep, ret)
                    if not data: continue
                    best_offer = min(data, key=lambda o: float(o["price"]["total"]))
                    best = float(best_offer["price"]["total"]) 
                    # haal basale carrier/stops/layover
                    try:
                        segs = best_offer["itineraries"][0]["segments"]
                        stops = len(segs)-1
                        carrier = segs[0]["carrierCode"]
                        lay = 0.0
                        for i in range(len(segs)-1):
                            a = dt.datetime.fromisoformat(segs[i]["arrival"]["at"].replace("Z","+00:00"))
                            b = dt.datetime.fromisoformat(segs[i+1]["departure"]["at"].replace("Z","+00:00"))
                            lay += (b-a).seconds/3600
                        lay = round(lay,1)
                    except Exception:
                        carrier, stops, lay = "N/A", 1, 2.0
                    row = {
                        "country":"AUTO","origin":orig,"destination_iata":dst,
                        "outbound_date":dep,"return_date":ret,
                        "trip_length_days": (dt.datetime.fromisoformat(ret)-dt.datetime.fromisoformat(dep)).days,
                        "days_before_departure": (dt.datetime.fromisoformat(dep) - dt.datetime.combine(today, dt.time())).days,
                        "price_eur": int(best),"airline":carrier,"stops":stops,
                        "max_layover_hours": lay, "fetched_at": fetched
                    }
                    rows.append(row)
                except Exception:
                    pass
            cur += dt.timedelta(days=1)
        # kalender (nu & vorig jaar)
        cal_now  = calendar_cheapest(tok, orig, dst, YEAR_NOW)
        update_monthly_buckets(monthly_path, f"{orig}-{dst}", YEAR_NOW, cal_now)
        cal_prev = calendar_cheapest(tok, orig, dst, YEAR_PREV)
        update_monthly_buckets(monthly_path, f"{orig}-{dst}", YEAR_PREV, cal_prev)

    update_time_series(sample_path, rows)

if __name__ == '__main__':
    main()
