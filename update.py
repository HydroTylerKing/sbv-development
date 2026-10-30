"""Update the South Boise Village development report.

    python update.py            check the city for changes, refresh the map, rebuild sbv_report.html
    python update.py --build    rebuild sbv_report.html from data/projects.json only (no network)
    python update.py --no-map   check the city and rebuild, but keep the existing map
    add --public to any of these to also write public/index.html (the GitHub Pages site)

What it does automatically
  1. Pulls South Boise Village cases from the City of Boise Development Tracker.
  2. For every project in data/projects.json, finds its related Planning/Building records and lists each
     record's status and documents on permits.cityofboise.org.
  3. Compares with the last run and writes a changes report (data/changes/<date>.txt): new projects, projects
     that left the tracker, status changes, and newly posted documents. Documents worth acting on
     (appeals, noticing radius maps, approval letters, revised drawings, hearings) are marked "ACT ON THIS".
  4. Rebuilds the lot map from the county parcel layer (data/map.json).
  5. Sets the report date to today and writes sbv_report.html.

  Then auto.py applies the changes to data/projects.json by fixed rules: adds new projects, updates statuses,
  stages, timelines, flags and deadlines, adds new drawings and notice areas, and retires finished projects.
  Nobody needs to review anything. Hand edits to data/projects.json are kept and only change when the city
  posts something new about that project.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(DATA, "cache")
PROJECTS = os.path.join(DATA, "projects.json")
OUT = os.path.join(HERE, "sbv_report.html")



def run(script, *args, quiet=False):
    """Run one of the helper scripts with this same Python."""
    cmd = [sys.executable, os.path.join(HERE, script), *args]
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{script} {' '.join(args)} failed:\n{(r.stderr or r.stdout).strip()[-800:]}")
    if not quiet and r.stdout.strip():
        print(r.stdout.rstrip())
    return r.stdout


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def docs_of(snap):
    return snap.get("documents", [])


def appeal_end(more_details):
    m = re.search(r"Appeal Period End Date:\s*(\d{2}/\d{2}/\d{4})", more_details or "")
    return m.group(1) if m else None


def fetch_record(rid):
    """Status, details and document list of one city record, or None if it isn't public."""
    time.sleep(2)  # be gentle with the city's site
    outdir = os.path.join(CACHE, "records", rid)
    try:
        run("aca.py", rid, outdir, "--match", "(?!)", quiet=True)
    except RuntimeError as e:
        if "record page not found" in str(e):
            return None
        raise
    return load(os.path.join(outdir, "record.json"), None)


def fetch_related(pid, address, filed):
    out = os.path.join(CACHE, "related", f"{pid}.json")
    since = (dt.date.fromisoformat(filed or dt.date.today().isoformat()) - dt.timedelta(days=365)).isoformat()
    run("related.py", pid, address, out, "--since", since, quiet=True)
    return load(out, [])


def snapshot(rec, pid):
    docs = [" | ".join([d["cells"][0], d["cells"][-1]]) for d in rec.get("documents", [])]
    return {"status": rec.get("status"), "documents": docs, "appeal_end": appeal_end(rec.get("more_details_text")),
            "url": rec.get("detail_url"), "project": pid}


def check_city(data, report):
    today = dt.date.today().isoformat()
    for sub in ("", "related", "records"):
        os.makedirs(os.path.join(CACHE, sub), exist_ok=True)
    projects = data["projects"]

    # 1. tracker
    print("Checking the City of Boise Development Tracker...")
    run("tracker.py", os.path.join(CACHE, "tracker.json"), quiet=True)
    tracker = load(os.path.join(CACHE, "tracker.json"), {"projects": []})
    on_tracker = {p["project_id"]: p for p in tracker["projects"]}
    known = {p["id"] for p in projects} | {x["id"] for x in data.get("inactive", [])}
    for pid, t in on_tracker.items():
        if pid not in known:
            report.append(f"NEW PROJECT   {pid}  {t.get('address')}  {t.get('description')}  [{t.get('status')}]")
    for p in projects:
        if p["id"] not in on_tracker:
            report.append(f"NOT ON TRACKER {p['id']}  {p['address']}  (approved projects drop off the tracker; check the record status below)")

    # 2-3. records and documents
    prev = load(os.path.join(CACHE, "documents.json"), {})
    first_run = not prev
    seen, records_full = {}, {}
    for p in projects:
        print(f"Checking {p['address']} ...")
        records = {p["id"], p.get("primary_app") or p["id"]} | {a["id"] for a in p.get("applications", [])}
        try:
            run("related.py", p["id"], (p.get("lot_addresses") or [p["address"]])[0],
                os.path.join(CACHE, "related", f"{p['id']}.json"), "--since",
                (dt.date.fromisoformat(p.get("filed") or today) - dt.timedelta(days=365)).isoformat(), quiet=True)
            for r in load(os.path.join(CACHE, "related", f"{p['id']}.json"), []):
                if r["record_id"] not in records:
                    records.add(r["record_id"])
                    if r["record_id"] not in prev and not first_run:
                        report.append(f"NEW RECORD    {p['address']}: {r['record_id']} {r.get('type', '')} [{r.get('status', '')}]")
        except RuntimeError as e:
            report.append(f"WARNING       related records for {p['id']} not checked: {str(e).splitlines()[-1]}")
        for rid in sorted(records):
            try:
                rec = fetch_record(rid)
            except RuntimeError as e:
                report.append(f"WARNING       {rid} not checked: {str(e).splitlines()[-1]}")
                continue
            if rec is None:
                continue
            records_full[rid] = rec
            now = snapshot(rec, p["id"])
            seen[rid] = now
            if rec.get("detail_url"):
                data.setdefault("record_urls", {})[rid] = rec["detail_url"]
            old = prev.get(rid)
            if first_run or old is None:
                continue
            if old.get("status") != now["status"]:
                report.append(f"STATUS        {p['address']}: {rid} {old.get('status')} -> {now['status']}")
            if now["appeal_end"] and now["appeal_end"] != old.get("appeal_end"):
                report.append(f"APPEAL PERIOD {p['address']}: {rid} appeal period ends {now['appeal_end']}")
            for d in docs_of(now):
                if d not in old.get("documents", []):
                    report.append(f"NEW DOCUMENT  {p['address']}: {rid}  {d}")
    before = json.loads(json.dumps(prev))
    prev.update(seen)
    save(os.path.join(CACHE, "documents.json"), prev)
    if first_run:
        report.append("FIRST RUN     Saved the current documents as the starting point. The next run will list what changed.")
    return {"before": before, "now": seen, "records": records_full, "tracker": on_tracker, "first_run": first_run}


def main():
    data = load(PROJECTS, None)
    if data is None:
        sys.exit(f"Can't read {PROJECTS}")
    report = []
    if "--build" not in sys.argv:
        state = check_city(data, report)
        import auto
        auto.apply(data, state, report, fetch_record=fetch_record, fetch_related=fetch_related, run=run)
        data["updated"] = dt.date.today().isoformat()
        save(PROJECTS, data)
        if "--no-map" not in sys.argv:
            print("Rebuilding the lot map from the county parcel layer...")
            run("sbvmap.py", "build", PROJECTS, os.path.join(DATA, "map.json"))
        path = os.path.join(DATA, "changes", f"{dt.date.today().isoformat()}.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("\n".join(report or ["No changes found."]) + "\n")
        print("\n=== Changes ===")
        print("\n".join(report or ["No changes found."]))
        print(f"(saved to {os.path.relpath(path, HERE)})\n")
    run("build_report.py", PROJECTS, os.path.join(HERE, "images"), OUT)
    print(f"Done: {os.path.relpath(OUT, HERE)}")
    if "--public" in sys.argv:  # for GitHub Pages: the site is the public/ folder
        import shutil
        os.makedirs(os.path.join(HERE, "public"), exist_ok=True)
        shutil.copyfile(OUT, os.path.join(HERE, "public", "index.html"))
        print("Copied to public/index.html")


if __name__ == "__main__":
    main()
