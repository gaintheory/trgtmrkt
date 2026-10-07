"""Fake Frazer-shaped export for developing the pipeline without real data.

The output has the PII columns a real export has (filled with obviously fake
values) so the de-identifier is exercised honestly. Outcomes follow planted
rules, so tests can check the analyses recover them:
  * bigger down payment share  -> fewer bad outcomes
  * older / higher-mileage car -> more bad outcomes
  * pricier car                -> slower to sell, bigger gross
Nothing here is real or derived from real customers.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd

# Approximate Middle TN ZIPs, weighted toward the lot that would draw them.
LOT_ZIPS = {
    "smyrna": ["37167", "37086", "37130", "37129", "37128", "37127", "37013"],
    "la_vergne": ["37086", "37167", "37013", "37122", "37076"],
    "murfreesboro": ["37130", "37129", "37128", "37127", "37167", "37153"],
}
STOCK = [
    ("Chevrolet", "Malibu"), ("Chevrolet", "Impala"), ("Nissan", "Rogue"),
    ("Nissan", "Altima"), ("Ford", "F-150"), ("Ford", "Focus"),
    ("Honda", "Civic"), ("Toyota", "Corolla"), ("Hyundai", "Sonata"),
    ("Dodge", "Charger"),
]


def generate(n_per_lot: int = 300, seed: int = 7, today: date | None = None) -> dict[str, pd.DataFrame]:
    rng = random.Random(seed)
    today = today or date(2026, 10, 1)
    out: dict[str, pd.DataFrame] = {}
    for lot, zips in LOT_ZIPS.items():
        rows = []
        for i in range(n_per_lot):
            make, model = rng.choice(STOCK)
            year = rng.randint(2009, 2018)
            age = 2026 - year
            miles = int(max(30_000, rng.gauss(55_000 + age * 9_000, 18_000)))
            price = round(max(3_500, rng.gauss(9_800 - age * 380, 1_800)) / 50) * 50
            down_pct = min(0.4, max(0.03, rng.gauss(0.14, 0.07)))
            down = round(price * down_pct)
            financed = price - down
            apr = rng.choice([19.99, 22.99, 24.99, 29.99])
            term = rng.choice([52, 78, 104])  # weekly/biweekly style counts
            pay = round(financed * (1 + apr / 100 * term / 104) / term, 2)

            risk = 0.10 + 0.012 * age + miles / 1_500_000 - 0.7 * (down_pct - 0.14)
            risk = min(0.6, max(0.02, risk))
            sale_date = today - timedelta(days=rng.randint(30, 900))
            r = rng.random()
            repo_out = ""
            status = "Active"
            dpd = ""
            if r < risk * 0.55:
                status = "Repossessed"
                max_off = max(1, (today - sale_date).days)
                repo_out = (sale_date + timedelta(days=rng.randint(min(45, max_off), max_off))
                            ).strftime("%m/%d/%Y")
            elif r < risk:
                status = "Active"
                dpd = str(rng.randint(60, 140))  # seriously delinquent, not yet repo'd
            elif r < risk + 0.30:
                status = "Paid Off"
            elif rng.random() < 0.25:
                dpd = str(rng.randint(1, 45))

            days_on_lot = max(2, int(rng.gauss(18 + (price - 3_500) / 250, 9)))
            cost = round(price * rng.uniform(0.45, 0.62))
            home = rng.choice(zips)
            rows.append({
                "Stock #": f"{lot[:2].upper()}{1000 + i}",
                "First Name": rng.choice(["Alex", "Sam", "Jordan", "Casey", "Riley"]),
                "Last Name": f"Testperson{i}",
                "Street": f"{rng.randint(1, 9999)} Fake St",
                "City": "Nowhere", "State": "TN", "Zip": f"{home}-0000",
                "Home Phone": "(615) 555-0100", "Email": f"fake{i}@example.invalid",
                "Birthday": "01/01/1980", "License Number": "000000000",
                "Employer": "Example Co", "Credit Score": "512",
                "Customer Income": "$38,000.00",
                "Vehicle VIN": f"SYNTH{i:012d}"[:17],
                "Year": year, "Make": make, "Model": model,
                "Mileage At Sale": miles, "Sale Date": sale_date.strftime("%m/%d/%Y"),
                "Sales Price": f"${price:,.2f}", "Down Payment": f"${down:,.2f}",
                "Amt Financed": f"${financed:,.2f}", "APR": apr,
                "Number of Payments": term, "Payment Amt": f"${pay:,.2f}",
                "Pay Schedule": "Weekly" if term == 52 else "Biweekly",
                "Total Cost": f"${cost:,.2f}",
                "Profit On Sale": f"${price - cost + rng.randint(-400, 600):,.2f}",
                "Days On Lot": days_on_lot,
                "Days past Due": dpd, "Account Status": status,
                "Repo Date Out": repo_out,
            })
        out[lot] = pd.DataFrame(rows)
    return out


def acs(seed: int = 11) -> pd.DataFrame:
    """Fake ACS-shaped demographics for the demo ZIPs. Not real."""
    from .analysis.catchment import DEMO_CENTROIDS
    rng = random.Random(seed)
    rows = []
    for z in DEMO_CENTROIDS:
        hh = rng.randint(4_000, 14_000)
        under = int(hh * rng.uniform(0.25, 0.5))
        rows.append({"zip5": z, "households": hh, "hh_under_50k": under,
                     "pct_hh_under_50k": under / hh,
                     "median_hh_income": rng.randint(38_000, 78_000),
                     "renter_share": rng.uniform(0.25, 0.55),
                     "no_vehicle_share": rng.uniform(0.03, 0.10),
                     "poverty_rate": rng.uniform(0.07, 0.2),
                     "unemployment_rate": rng.uniform(0.02, 0.06)})
    return pd.DataFrame(rows)
