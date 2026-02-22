# Ivo's Flighttracker — Automatische updates (2×/dag)

Dit pakket bevat alles om jouw Netlify‑site te voeden via GitHub Actions.

## Wat zit erin?
- `index.html`, `assets/` → UI met extra grafiek "Laagste prijs per maand (week‑buckets)".
- `data/sample_data.json` (leeg) → wordt automatisch gevuld.
- `data/monthly_lowest.json` (leeg) → wordt automatisch gevuld (2026 én 2025).
- `tools/fetch_prices.py` → haalt prijzen op via Amadeus en bouwt de JSON‑bestanden.
- `.github/workflows/fare-cron.yml` → draait 2×/dag en pusht de nieuwe data (Netlify autodeployt).

## Eenmalige installatie
1) **Repository**: maak een GitHub‑repo en upload deze map als root.
2) **Secrets**: in GitHub → Settings → Secrets → Actions → voeg toe:
   - `AMADEUS_API_KEY`
   - `AMADEUS_API_SECRET`
3) **Netlify**: koppel je site aan deze GitHub‑repo (Site settings → Build & deploy → Link to a Git provider). Elke push deployt automatisch.

## Werking
- Routes (2×/dag): AMS/EIN → LIS, OPO, BKK, ZAG, SPU.
- Zomerwindow: 18 juli – 26 aug 2026, duur ~21±2 dagen.
- Tijdreeks (`sample_data.json`): voor de grafiek "Beste aankoopmoment".
- Maandgrafiek (`monthly_lowest.json`): 12 maanden × 4 week‑buckets; bevat ook 2025 als referentie.

> Let op: eerste run kan ~10–20 min duren (API‑calls). Daarna zie je data in het dashboard.

Gemaakt: 2026-02-22 17:11 UTC
