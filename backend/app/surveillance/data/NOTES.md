# Data Sources — Surveillance Fixture

## owid_fixture.csv

This file contains an OWID-derived, approximated subset of historical disease
outbreak data for EpiWatch development and demonstration purposes.

**Original source:**  Our World in Data (OWID)
**License:**          Creative Commons Attribution 4.0 (CC BY)
**OWID URL:**         https://ourworldindata.org/
**COVID-19 source:**  https://github.com/owid/covid-19-data (CC BY)
**Measles source:**   https://ourworldindata.org/measles (CC BY / WHO data)
**Dengue source:**    https://ourworldindata.org/dengue (CC BY / WHO/PAHO data)
**Cholera source:**   https://ourworldindata.org/cholera (CC BY / WHO data)

### Attribution

The fixture data is derived from and approximates OWID datasets (CC BY).
Numbers are rounded and some months/years are interpolated to produce a
compact fixture of ~320 rows.  For authoritative figures, use the original
OWID datasets at the URLs above.

Our World in Data is a project of Global Change Data Lab, a registered
charity in England and Wales (Charity Number 1186433).

### Diseases included

| Disease     | Regions              | Granularity | Period        |
|-------------|----------------------|-------------|---------------|
| covid_19    | India, United States, Brazil, Germany | Monthly | 2020-03–2023-06 |
| measles     | India, Nigeria, Ethiopia, Pakistan, Indonesia | Annual | 2000–2022 |
| dengue      | India, Brazil, Philippines, Indonesia | Annual | 2012–2022 |
| cholera     | India, Yemen, DRC | Annual | 2010–2022 |

### Column definitions

- `disease_name` — Slug identifier (underscores, lowercase)
- `region`       — Country name as used in OWID datasets
- `date`         — YYYY-MM-DD; first of month for monthly data, YYYY-01-01 for annual
- `case_count`   — Confirmed cases for the period
- `deaths`       — Attributed deaths for the period (0 if not reported)
- `source`       — Always "OWID" for this fixture
