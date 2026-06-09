"""
Generate owid_fixture.csv — approximate OWID-derived outbreak data.

Run from repo root:
  python -m app.surveillance._gen_fixture

The output is committed to data/owid_fixture.csv so the ingest script
never needs internet access.  Re-run this only when you want to refresh
the fixture shape; the dataset itself should be stable.

Data attribution: Our World in Data (CC BY 4.0)
  https://ourworldindata.org/
"""
import csv
import math
from datetime import date
from pathlib import Path

OUT = Path(__file__).parent / "data" / "owid_fixture.csv"
HEADER = ["disease_name", "region", "date", "case_count", "deaths", "source"]


def gauss(x: float, mu: float, sigma: float, amp: float) -> float:
    return amp * math.exp(-((x - mu) ** 2) / (2 * sigma ** 2))


def month_seq(start: date, n: int):
    """Yield the first day of each calendar month for n months from start."""
    y, m = start.year, start.month
    for _ in range(n):
        yield date(y, m, 1)
        m += 1
        if m > 12:
            m = 1
            y += 1


# ── COVID-19 monthly data (OWID-derived approximation) ────────────────────────

def covid_india() -> list[tuple]:
    """India: three Gaussian waves (Sep 2020 / May 2021 / Jan 2022)."""
    rows = []
    start = date(2020, 3, 1)
    for i, d in enumerate(month_seq(start, 40)):
        # Wave 1: peak month 6 (Sep 2020); Wave 2: month 15 (May 2021);
        # Wave 3: month 23 (Jan 2022)
        cases = int(
            gauss(i,  6, 2.5,  2_700_000) +
            gauss(i, 15, 1.5, 11_920_000) +
            gauss(i, 23, 1.8,  7_620_000) +
            max(0, (10 - i) * 8_000)         # pre-wave background
        )
        cases = max(500, cases)
        cfr = 0.016 if i < 18 else 0.008 if i < 24 else 0.003
        rows.append(("covid_19", "India", d.isoformat(), cases, int(cases * cfr), "OWID"))
    return rows


def covid_usa() -> list[tuple]:
    """USA: winter 2020-21 surge, Delta (Aug-Sep 2021), Omicron (Jan 2022)."""
    rows = []
    start = date(2020, 3, 1)
    for i, d in enumerate(month_seq(start, 40)):
        cases = int(
            gauss(i,  9, 1.8,  6_380_000) +   # Dec 2020 / winter surge
            gauss(i, 10, 1.2,  5_240_000) +   # Jan 2021
            gauss(i, 18, 2.0,  2_700_000) +   # Delta Aug-Sep 2021
            gauss(i, 23, 1.5, 20_000_000) +   # Omicron Jan 2022
            gauss(i, 24, 1.2,  5_700_000) +   # Omicron tail
            max(0, (8 - i) * 40_000)           # early background
        )
        cases = max(1_000, cases)
        cfr = 0.060 if i < 6 else 0.018 if i < 20 else 0.008 if i < 25 else 0.004
        rows.append(("covid_19", "United States", d.isoformat(), cases, int(cases * cfr), "OWID"))
    return rows


def covid_brazil() -> list[tuple]:
    """Brazil: Gamma variant drove a brutal second wave (Mar-Jun 2021)."""
    rows = []
    start = date(2020, 3, 1)
    for i, d in enumerate(month_seq(start, 40)):
        cases = int(
            gauss(i,  5, 2.0,  1_200_000) +   # Wave 1 (Jul 2020)
            gauss(i, 13, 1.8,  2_250_000) +   # Wave 2 (Apr 2021 / Gamma)
            gauss(i, 15, 1.5,  3_410_000) +   # Wave 2 peak (Jun 2021)
            gauss(i, 23, 1.5,  4_160_000) +   # Omicron Jan 2022
            max(0, (5 - i) * 15_000)
        )
        cases = max(200, cases)
        cfr = 0.030 if i < 16 else 0.012 if i < 24 else 0.005
        rows.append(("covid_19", "Brazil", d.isoformat(), cases, int(cases * cfr), "OWID"))
    return rows


def covid_germany() -> list[tuple]:
    """Germany: four distinct waves, high reporting quality."""
    rows = []
    start = date(2020, 3, 1)
    for i, d in enumerate(month_seq(start, 40)):
        cases = int(
            gauss(i,  7, 2.0,    520_000) +   # Wave 1 (Oct 2020)
            gauss(i,  9, 1.5,    730_000) +   # Wave 2 (Dec 2020)
            gauss(i, 12, 1.5,    560_000) +   # Wave 3 (Mar 2021)
            gauss(i, 20, 2.0,  1_210_000) +   # Wave 4 (Nov 2021)
            gauss(i, 23, 1.8,  8_650_000) +   # Omicron Jan 2022
            max(0, (3 - i) * 5_000)
        )
        cases = max(100, cases)
        cfr = 0.022 if i < 10 else 0.008 if i < 22 else 0.003
        rows.append(("covid_19", "Germany", d.isoformat(), cases, int(cases * cfr), "OWID"))
    return rows


# ── Measles annual data (WHO/OWID-derived approximation) ─────────────────────
# Measles case counts decline globally as vaccination coverage improves,
# with periodic outbreaks when coverage drops.

_MEASLES: dict[str, list[int]] = {
    # India: declining trend with a major outbreak in 2018-19 (vaccine hesitancy)
    "India": [
        87000, 53000, 52000, 45000, 42000,  # 2000-2004
        38000, 37000, 80000, 56000, 56000,  # 2005-2009
        29000, 19000, 19000, 36000, 23000,  # 2010-2014
        18000,  9600, 14000, 56000, 61000,  # 2015-2019
         6800, 12000, 18000,               # 2020-2022
    ],
    # Nigeria: high burden, periodic outbreaks; recent surge due to conflict
    "Nigeria": [
        24000, 18000, 20000, 15000, 18000,  # 2000-2004
        12000, 14000, 11000, 16000, 14000,  # 2005-2009
        15000, 10000,  9200,  8500,  8000,  # 2010-2014
         7200,  6800,  6100, 25000, 30000,  # 2015-2019
        18000, 22000, 28000,               # 2020-2022
    ],
    # Ethiopia: strengthening EPI program, dramatic decline
    "Ethiopia": [
        32000, 28000, 24000, 20000, 16000,  # 2000-2004
        14000, 11000,  9000, 12000,  8500,  # 2005-2009
         7000,  5500,  4800,  3900,  3200,  # 2010-2014
         2800,  2200,  3500,  1900,  1400,  # 2015-2019
         1100,  1800,  2100,               # 2020-2022
    ],
    # Pakistan: stubborn reservoir due to vaccine refusal in some regions
    "Pakistan": [
        18000, 15000, 13000, 17000, 14000,  # 2000-2004
        12000, 10000,  8000, 11000, 14000,  # 2005-2009
        16000, 20000, 14000,  7200,  6500,  # 2010-2014
         8900, 11000, 14000, 18000, 16000,  # 2015-2019
         9800, 12000, 14000,               # 2020-2022
    ],
    # Indonesia: archipelago logistics challenge; improved after SIAs
    "Indonesia": [
        10000,  8500,  7200,  6100,  5200,  # 2000-2004
         4800,  3900,  5100,  3500,  2900,  # 2005-2009
         2200,  1900,  2800,  1600,  1200,  # 2010-2014
         1100,   950,  2100,  3400,  4800,  # 2015-2019
         2100,  1800,  2400,               # 2020-2022
    ],
}


def measles_rows() -> list[tuple]:
    rows = []
    for region, counts in _MEASLES.items():
        for yr_offset, count in enumerate(counts):
            yr = 2000 + yr_offset
            rows.append(("measles", region, f"{yr}-01-01", count, int(count * 0.001), "OWID"))
    return rows


# ── Dengue annual data (WHO/OWID-derived approximation) ──────────────────────

_DENGUE: dict[str, list[int]] = {
    # India: NVBDCP annual reports; strong monsoon seasonality
    "India": [
        50222, 75808, 68031, 75808, 89013, 99913, 121085, 157395, 188401, 193000, 157315,
    ],
    # Brazil: largest dengue burden in the Americas; 2015 megaoutbreak
    "Brazil": [
        1449924, 1473489, 770854, 234031, 702238, 327281, 421529, 217883, 653717, 2272256, 871592,
    ],
    # Philippines: year-round transmission; major outbreak 2019
    "Philippines": [
        165123, 170000, 138600, 117621, 126895, 122749, 206100, 154843, 180000, 437563, 97246,
    ],
    # Indonesia: high underreporting; climate-sensitive
    "Indonesia": [
        114656, 156086, 173480, 204171, 126675, 126614, 129179, 71668, 100347, 137119, 95893,
    ],
}
_DENGUE_START = 2012


def dengue_rows() -> list[tuple]:
    rows = []
    for region, counts in _DENGUE.items():
        for yr_offset, count in enumerate(counts):
            yr = _DENGUE_START + yr_offset
            rows.append(("dengue", region, f"{yr}-01-01", count, int(count * 0.003), "OWID"))
    return rows


# ── Cholera annual data (WHO/OWID-derived approximation) ─────────────────────

_CHOLERA: dict[str, list[int]] = {
    # India: relatively contained; strong WASH programs
    "India": [5000, 4200, 3800, 5100, 4600, 4100, 3700, 6200, 4800, 4100, 3900, 3600, 3200],
    # Yemen: catastrophic 2016-2019 outbreak (world's worst cholera crisis)
    "Yemen": [200, 350, 500, 680, 750, 820, 500000, 700000, 371000, 320000, 312000, 138000, 95000],
    # DRC: endemic with repeated outbreaks
    "DRC":   [14000, 18000, 21000, 32000, 28000, 22000, 31000, 21000, 15000, 17000, 20000, 24000, 28000],
}
_CHOLERA_START = 2010


def cholera_rows() -> list[tuple]:
    rows = []
    for region, counts in _CHOLERA.items():
        for yr_offset, count in enumerate(counts):
            yr = _CHOLERA_START + yr_offset
            cfr = 0.04 if region == "Yemen" and yr in (2016, 2017) else 0.012
            rows.append(("cholera", region, f"{yr}-01-01", count, int(count * cfr), "OWID"))
    return rows


def main() -> None:
    rows = (
        covid_india() +
        covid_usa() +
        covid_brazil() +
        covid_germany() +
        measles_rows() +
        dengue_rows() +
        cholera_rows()
    )

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)

    by_disease: dict[str, int] = {}
    for row in rows:
        by_disease[row[0]] = by_disease.get(row[0], 0) + 1

    print(f"wrote {len(rows)} rows to {OUT}")
    for disease, count in sorted(by_disease.items()):
        print(f"  {disease}: {count} rows")


if __name__ == "__main__":
    main()
