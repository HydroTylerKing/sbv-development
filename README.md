# South Boise Village development report

A public web page that tracks active zoning and planning cases in the South Boise Village neighborhood of Boise, Idaho. Each project shows:

- key attributes (zoning, lot, units, size, height, setbacks, parking, access) taken from the city's documents;
- an approval timeline, and flags for anything neighbors may want to weigh in on (variances, appeals, hearings, comment deadlines);
- the most recent drawings from the City of Boise case files, with private details redacted;
- a lot map with each project's notice area, drawn from the city's noticing radius maps.

**Live page:** https://hydrotylerking.github.io/sbv-development/

This is a screening tool built from public records. It is not an official city record and can be incomplete or out of date.

## How it stays current

A GitHub Actions workflow (`.github/workflows/daily.yml`) runs every morning:

1. checks the City of Boise Development Tracker and every project's case records for status changes and new documents;
2. redraws the lot map from the county parcel layer;
3. rebuilds the page and publishes it to GitHub Pages;
4. saves the day's results to `data/` and, when the city posted something that needs a person, **opens a GitHub issue** listing it.

The workflow finds changes. A person reads the new city documents and updates `data/projects.json`, following [EDITING_GUIDE.md](EDITING_GUIDE.md). Committing to `main` republishes the page.

- Setting up, running and handing off: **[DEPLOY.md](DEPLOY.md)**
- Editing the report's content: **[EDITING_GUIDE.md](EDITING_GUIDE.md)**

## Files

| File | Purpose |
|---|---|
| `update.py` | Runs everything in order (`--build` to rebuild only, `--public` to also write `public/index.html`) |
| `tracker.py` | City of Boise Development Tracker (ArcGIS open data) |
| `aca.py` | Case records and documents on permits.cityofboise.org |
| `related.py` | Related Planning/Building records on the same property |
| `sbvmap.py` | Lot map and notice areas (county parcels, neighborhood boundary) |
| `redact.py` | Renders a drawing, blacks out private details, stamps the City of Boise source |
| `build_report.py` | Builds the page from `data/projects.json`, `data/map.json` and `images/` |
| `ci_tools.py` | Workflow helpers: open the daily issue, save results |
| `data/projects.json` | The report's content (edited by hand) |
| `data/map.json` | Map geometry (regenerated every run) |
| `data/cache/documents.json` | Last-seen statuses and documents, used to spot changes |
| `data/changes/` | One changes report per day |
| `images/` | Redacted drawings |

## Run it on your own computer

```
pip install -r requirements.txt
python update.py            # check the city, redraw the map, build sbv_report.html (~5 minutes)
python update.py --build    # rebuild sbv_report.html from data/projects.json only
```
Adding drawings also needs poppler and tesseract; see DEPLOY.md.

## Public data sources

- City of Boise Development Tracker: https://www.cityofboise.org/departments/planning-and-development-services/planning/zoning/maps/development-tracker/
- City of Boise Permitting & Licensing (case files): https://permits.cityofboise.org/CitizenAccess/Default.aspx
- Ada County parcels and Boise neighborhood association boundaries: City of Boise ArcGIS open data (services1.arcgis.com)
- Boise City Code, Title 11 (zoning): https://codelibrary.amlegal.com/codes/boise_id/latest/overview
