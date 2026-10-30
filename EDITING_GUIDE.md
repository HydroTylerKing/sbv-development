# Editing guide: keeping the report accurate

`data/projects.json` is the report's content. The daily workflow finds changes; a person decides what they mean and edits this file. These are the rules the report has followed since it started. Keep to them so the page stays consistent, factual and free of private information.

**Three rules above all**
- Use only what the City of Boise's documents state. Write "Not shown" when a document doesn't say. Never guess or estimate.
- Never put a private person's name, phone, email or home address on the page: owners, applicants who are private persons, appellants, neighbors. Companies, architects, engineers, surveyors and city staff (as named in city notices) are fine.
- Keep wording neutral: what is requested, what the city decided or scheduled, and dates. No opinions or predictions.

## Links on the page (keep these filled in)
- `record_urls` (top level of data/projects.json): record id → its case page URL. aca.py writes `detail_url` into each record.json; add every record you open. The page links application ids, the project case file and image sources through this map (it falls back to a search link).
- `primary_app` (per project): the record the overview's Application column links to: the main active application (for example the ADU zoning certificate or the subdivision), or the PLN project if no application is filed yet.
- Every image needs `"source": {"record": "<record id>", "document": "<document name exactly as listed on the case>", "uploaded": "<MM/DD/YYYY upload date>", "page": <PDF page number>}`. The city site has no per-document URLs (files download through a page postback), so the page links to the case record and names the document.

## Drawings: redact and stamp every image (required)
Never publish a drawing image without running it through redact.py:
`python redact.py IN.pdf PAGE images/<slug>.jpg --record <case id> --retrieved <today> --terms "<private names>" ... --preview check.png --dpi <dpi>`
(pick dpi so the page renders about 3600 px wide: dpi = 3600 / (page width in inches), between 100 and 220).
- It blacks out every phone number and email automatically. Pass with --terms every private individual's name on the sheet: owners, applicants who are private persons, neighbors labeled on plats, and an owner's surname used as a project name (e.g. "Smith ADU"). Companies, architects, engineers, surveyors and drafters stay.
- Read the sheet first (render it at ~60 dpi and look) to find the names. After redacting, LOOK at the preview and confirm nothing private remains; if OCR missed something, add `--box x0,y0,x1,y1` (fractions of the page) and run again.
- The script stamps a band reading "Source: City of Boise Planning & Development Services, public case file <id> (permits.cityofboise.org) · retrieved <date> · private details redacted". Also set the image's `source.retrieved` and `source.redacted: true`.

## Maps and notice areas
- Each project needs `lot_addresses`: its site address(es) exactly as the county parcel layer lists them (e.g. "1911 S MANITOU AVE").
- Notice areas come only from the city. When an application reaches public notice the city uploads "PDS-Maps and Drawings - NOTICING RADIUS MAP" (and a legal notice) to it. When one appears on any record of a project, download it and run `python sbvmap.py notice "<pdf>" "<subject address>"`, then set the project's `notice` to `{"kind": "<e.g. Administrative decision notice / Hearing Examiner hearing notice>", "record": "<case id>", "document": "<document name>", "uploaded": "<MM/DD/YYYY>", "addresses": [<printed list>]}`. If the script cannot read the map (some maps have unreadable text), render it, read the shaded parcels' addresses yourself and enter them.
- A staff report that states a distance instead ("radius notices mailed to properties within 500 feet") → `"notice": {"kind": ..., "record": ..., "document": ..., "radius_ft": 500, "basis": "<quote>"}`.
- A newer notice (for example an appeal hearing) replaces the older one; add a changelog entry.
- Do not draw notice areas for withdrawn applications. Never estimate a notice area the city has not published.
- Every run: `python sbvmap.py build data/projects.json data/map.json` before build_report.py (it fetches parcels and the neighborhood boundary live).

## Approved projects leave the tracker
The city's Development Tracker drops a project once it is approved or entitled (1113 W Garfield St dropped out on Oct 24 after its Oct 23 approval). A project missing from the tracker is NOT withdrawn: check its records with aca.py. If approved, keep it active at step 4 until its appeal period ends (case "More Details" shows "Appeal Period End Date"), then step 5 "Approved"; move it to `inactive` with note "Approved <date>; no appeal" 30 days after the appeal period ends. Only call a project withdrawn or expired when the city's record status says so.

## Neighbor input flags (keep current every run)
Each project has `flags`: `[{"type", "status", "label", "detail", "record", "deadline"?}]`, and optionally `contact` `{"planner", "email", "phone", "source"}` taken only from a city notice or letter (city staff contact details are fine to show; never a private person's).
- status: `open` (input can be given now, with a deadline), `upcoming` (a hearing, appeal or application that will open input), `info` (worth reviewing, no formal input step), `past` (closed; keep for context).
- Raise a flag, from the city's records only, when you see:
  - variance: any CVA record, or a narrative asking for one → `variance` (upcoming while pending; past once decided or withdrawn).
  - appeal: a "PDS-Appeals" document → `appeal`, upcoming until the hearing is held; add the hearing date to detail and `deadline` once set.
  - appeal window: an approval whose case "More Details" shows an Appeal Period End Date in the future → `appeal_window`, status open, `deadline` = that date; switch to past the day after.
  - hearing: a public hearing (Hearing Examiner, Planning & Zoning, City Council) scheduled or pending, from the tracker's NextHearingDate/HearingBody, legal notices or action letters → `hearing` (open with deadline = hearing date once set; upcoming before).
  - nonconforming (LNC applications), subdivision or lot split (SUB, minor land division), demolition, design review (DRH), accessory structures over 1,000 SF or 22 ft, street or canal changes, neighborhood meetings (NBR; upcoming if scheduled, past when complete).
- Wording stays factual and neutral: what is requested, what the city decided or scheduled, and dates. No opinions, no predictions.
- A new open or upcoming flag, a new deadline, or a scheduled hearing date is a change: add a changelog entry so it is recorded.

## Change log
`data/projects.json` has a top-level `changelog` list. For every change a run finds, append `{"date": "<today>", "project": "<PLN id>", "address": "...", "change": "<one plain sentence>"}`. Changes are: new projects, new related or child records, status changes (approvals, appeals, returns, withdrawals), hearings scheduled or held, new or revised drawings, projects moved to inactive. A refreshed `updated` date alone is not a change. Drop entries older than 60 days.

## When the daily check opens an issue
The workflow already did the mechanical part: it checked the tracker and every record, listed new documents and status changes, redrew the map and republished the page. Your job is to read what changed and update `data/projects.json`:

1. Open each listed case on permits.cityofboise.org (the case number links on the report go straight there) and read the new documents.
   To download documents from the command line: `python aca.py CASE-ID downloads --match 'ELEV|PLAN SET|RENDER|SITE PLAN|LETTER OF|PROJECT DESC|Concept Review|PROJECT REPORT|ACTION LETTER|APPEAL|NOTIC'`.
   Records not yet public return "record page not found"; skip them.
2. Update the project per the rules above:
   - Status changes and new documents (listed in the issue) → update `stage`, `stage_tone`, `next_step`, `last_activity`, `applications`, `timeline` and `flags`.
   - Projects that disappeared or show Expired/Withdrawn/Closed → move to `inactive` with a one-line note.
   - New child records under an existing project → add to `applications`.
   - **New related records** (listed as NEW RECORD) → add each to `applications` with its type and current status, and read its documents like the parent's. The workflow finds them with `related.py`, which keeps only Planning and Building records at the same address.
   - **Always show the most recent plans.** When any record on the property (parent, child, related, or a building permit) has newer drawings than the ones on the page (look for "V2", "REVISED", "UPDATED" or a later upload date), download them and replace the page's images, noting the date and record in the caption, e.g. "Revised elevations V2, 9/23/26 (CZC26-00227)". Re-check attributes against the newest plans and approval letter.
   - Watch for "PDS-Appeals" documents on any record. An appeal filed against an approval sets the timeline to step 4 with `"flag": "appealed"`, stage "Approval under appeal", stage_tone "attention"; record the hearing date once the city schedules it. Never put an appellant's or private owner's name or home address on the page (the page is public); companies and design professionals are fine.
   - An approval or action letter on any related record moves the timeline: approved administratively → step 5 "Approved" (note the appeal period end date from the case's "More Details"); a decision still inside its appeal period → step 4.
   - The permit site can be slow or return 503. aca.py retries with backoff; don't run downloads in parallel.
   - **New project or newly posted drawings:** download narratives, concept review summary, staff report/action letter, site plan and any elevation/plan set (`aca.py ID out --match 'ELEV|PLAN SET|RENDER|SITE PLAN|LETTER OF|PROJECT DESC|Concept Review|PROJECT REPORT|ACTION LETTER'`). Records not yet public return "record page not found": skip them.
   - Find elevation pages: pdfplumber text search for "ELEVATION" per page, then render candidates at ~40 dpi and LOOK at them to confirm. Prefer clean line elevations over marked-up copies; renderings are fine as a second image.
   - Produce every image with `redact.py` (see "Drawings" above), never by exporting the PDF directly. Then add it to the project's `images` with its `source`.
   - If no elevations exist, use the plat or site plan and say "(no elevations filed)" in the caption.
   - Fill all 8 attributes (Zoning, Lot, Units, Size, Height, Setbacks, Parking, Access) from the documents and the case page "More Details" text (zoning district, lot size, ADU SF, bedrooms). Use only what the documents state; write "Not shown" when unknown. Never guess.
   - Update each project's `timeline`: `{"step": N, "flag": null|"returned"|"appealed", "note": "...", "dates": {"N": "YYYY-MM-DD"}}`.
     Steps: 0 Concept (concept review held, no applications filed yet) · 1 Filed (applications received) · 2 Review (city/agency review under way; also use with flag "returned" when an application was returned to the applicant; `flag` may be null, "returned" or "appealed") · 3 Hearing (public notice posted, neighborhood meeting, or hearing/commission recommendation; Council still to decide) · 4 Decision (final decision issued but appeal period or conditions pending) · 5 Approved.
     `dates` records the date each step was reached when the documents show it (concept review summary date, application received date, legal notice or hearing date, action letter date). `note` is one short line on where it stands and what comes next.
3. A brand-new project: add an entry to `projects` modeled on an existing one (copy a similar project and replace every field). Give it `"first_seen": "<today>"` and `lot_addresses`; the page shows "New this week" for 7 days. Never change an existing `first_seen`.
4. Order `projects` by `last_activity`, newest first. Add a `changelog` entry for each change.
5. Check locally with `python update.py --build` and open `sbv_report.html`, then commit to `main`. The workflow republishes the page within a few minutes. Close the issue.
