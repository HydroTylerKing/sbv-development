# South Boise Village development report

A public web page that tracks active zoning and planning cases in the South Boise Village neighborhood of Boise, Idaho. Each project shows:

- key attributes (zoning, lot, units, size, height, setbacks, parking, access) taken from the city's documents;
- an approval timeline, and flags for anything neighbors may want to weigh in on (variances, appeals, hearings, comment deadlines);
- the most recent drawings from the City of Boise case files (phone numbers and emails blacked out);
- a lot map with each project's notice area, drawn from the city's noticing radius maps.

**Live page:** https://hydrotylerking.github.io/sbv-development/

This is a screening tool built from public records. It is not an official city record and can be incomplete or out of date.

## How it stays current

**Fully automatic.** A GitHub Actions workflow (`.github/workflows/daily.yml`) runs every morning and nobody needs to review anything:

1. checks the City of Boise Development Tracker and every project's case records, including related records on the same property;
2. applies what changed by fixed rules (`auto.py`):
   - **new projects** are added with the details the city publishes: description, zoning, lot size, units and parking from the city's concept review, applications, drawings and notice area;
   - **status changes** update the stage, timeline and next step: approvals, returns, withdrawals;
   - **appeals, hearing dates and appeal deadlines** become neighbor flags, and close on their own when the date passes;
   - **new drawings** (elevations, renderings, plan sets, otherwise site plans or plats) are rendered with the City of Boise source stamped on them;
   - **notice areas** are read from the city's noticing radius maps;
   - **finished projects** (withdrawn, expired, or approved with no appeal for 30 days) move to "Not shown";
3. redraws the lot map, rebuilds the page and publishes it to GitHub Pages;
4. saves the day's results to the repository and lists every change in "Recent changes" on the page.

Hand edits to `data/projects.json` are optional: use them to add detail or correct a wording. They are kept until the city posts something new about that project. See [EDITING_GUIDE.md](EDITING_GUIDE.md).

- Setting up and running: **[DEPLOY.md](DEPLOY.md)**
- Optional hand edits: **[EDITING_GUIDE.md](EDITING_GUIDE.md)**

## Files

| File | Purpose |
|---|---|
| `update.py` | Runs everything in order (`--build` to rebuild only, `--public` to also write `public/index.html`) |
| `auto.py` | The rules that apply each day's city changes to the report automatically |
| `tracker.py` | City of Boise Development Tracker (ArcGIS open data) |
| `aca.py` | Case records and documents on permits.cityofboise.org |
| `related.py` | Related Planning/Building records on the same property |
| `sbvmap.py` | Lot map and notice areas (county parcels, neighborhood boundary) |
| `redact.py` | Renders a drawing, stamps the City of Boise source, blacks out phone numbers and emails |
| `build_report.py` | Builds the page from `data/projects.json`, `data/map.json` and `images/` |
| `ci_tools.py` | Workflow helper: saves each day's results to the repository |
| `data/projects.json` | The report's content (updated automatically; hand edits optional) |
| `data/map.json` | Map geometry (regenerated every run) |
| `data/cache/documents.json` | Last-seen statuses and documents, used to spot changes |
| `data/changes/` | One changes report per day |
| `images/` | Drawings shown on the page |

## Run it on your own computer

```
pip install -r requirements.txt
python update.py            # check the city, redraw the map, build sbv_report.html (~5 minutes)
python update.py --build    # rebuild sbv_report.html from data/projects.json only
```
A full run also needs poppler and tesseract for the drawings; see DEPLOY.md.

## Public data sources

- City of Boise Development Tracker: https://www.cityofboise.org/departments/planning-and-development-services/planning/zoning/maps/development-tracker/
- City of Boise Permitting & Licensing (case files): https://permits.cityofboise.org/CitizenAccess/Default.aspx
- Ada County parcels and Boise neighborhood association boundaries: City of Boise ArcGIS open data (services1.arcgis.com)
- Boise City Code, Title 11 (zoning): https://codelibrary.amlegal.com/codes/boise_id/latest/overview
