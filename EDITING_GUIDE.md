# Editing guide (optional)

The report updates itself every morning (see README.md), so you never have to edit anything. Use this guide if you want to add detail the automatic rules can't, such as height, setbacks or a better summary, or to correct a wording.

## How hand edits and automatic updates work together

- `data/projects.json` holds the report's content. Edit it in GitHub's web editor (open the file, click the pencil icon, commit) or on your computer.
- Committing to `main` republishes the page within a few minutes.
- The daily run changes a project **only when the city posts something new about it**: a status change, a new record, a new document, a new hearing date, or an appeal deadline passing. Then it rewrites the parts that changed (stage, next step, timeline, flags, applications, drawings, notice area). Your other text, such as the summary and attributes, is kept.
- If the JSON has a mistake, the run fails and GitHub emails the owner. The log names the line. Fix it and commit again.

## Content rules

- **Facts from the City of Boise's documents only.** Write "Not shown" when a document doesn't say. Never guess or estimate.
- **Neutral wording.** Say what is requested, what the city decided or scheduled, and dates. No opinions or predictions.
- **Contact details.** Drawings have phone numbers and emails blacked out automatically (`SBV_REDACT_CONTACTS` in the workflow). Names appear as they do in the city's public files.

## Project fields

| Field | What it holds |
|---|---|
| `address`, `name`, `kind` | Heading, project name, and type label such as "ADU" or "Subdivision" |
| `summary` | One or two plain sentences on what is proposed |
| `attributes` | Zoning, Lot, Units, Size, Height, Setbacks, Parking, Access ("Not shown" when unknown) |
| `stage`, `stage_tone` | Badge text, and its color: `early`, `review`, `attention`, `decision` |
| `next_step` | One sentence on what happens next |
| `timeline` | `step` 0–5 (Concept, Filed, Review, Hearing, Decision, Approved), `flag` (`null`, `"returned"` or `"appealed"`), `dates` (step → YYYY-MM-DD), `note` |
| `flags` | Neighbor-input items: `type`, `status` (`open`, `upcoming`, `info`, `past`), `label`, `detail`, `record`, optional `deadline` (YYYY-MM-DD). Flags with `"auto": true` are managed by the daily run |
| `contact` | Assigned city planner, as named in a city notice or letter: `planner`, `email`, `phone`, `source` |
| `applications`, `primary_app` | City case numbers shown, and the one the overview links to |
| `images` | Drawings shown, each with `file`, `kind`, `caption`, `source` (record, document name, upload date, page) |
| `lot_addresses` | Site address(es) exactly as the county parcel layer lists them, e.g. "1911 S MANITOU AVE" |
| `notice` | Notice area: `record`, `document`, `uploaded`, and either `addresses` (from the city's radius map) or `radius_ft` (when a staff report gives a distance) |
| `first_seen` | Date the project was first added; the page shows "New this week" for 7 days |

Top-level fields: `changelog` (the "Recent changes" list; the daily run adds to it), `inactive` (retired projects), `record_urls` (case number → city case page).

## Occasional fixes

**A notice map the run couldn't read.** Some city maps have text that can't be read by machine, and the run log says "notice map ... not read automatically". Open the map PDF from the case's Documents list and note the addresses of the shaded parcels. Then set the project's `notice`:
```json
"notice": {"kind": "Public notice", "record": "CZC26-00227", "document": "PDS-Maps and Drawings - NOTICING RADIUS MAP",
           "uploaded": "10/07/2026", "addresses": ["1919 S MANITOU AVE", "1920 S MANITOU AVE"]}
```
On your computer, `python sbvmap.py notice "<map>.pdf" "<project address>"` prints the list for maps it can read.

**A different drawing.** The run picks the newest elevation, rendering or plan-set document, otherwise the newest site plan or plat. To use a specific sheet instead, run this on your computer:
```
python aca.py CASE-ID downloads --match "ELEV"
python redact.py "downloads/<file>.pdf" PAGE images/<name>.jpg --record CASE-ID --retrieved YYYY-MM-DD
```
Then point the project's `images` entry at the new file. The next new drawing the city posts for that project replaces it.

**A project that should be hidden.** Move its entry from `projects` to `inactive` as `{"id": ..., "address": ..., "note": "..."}`.
