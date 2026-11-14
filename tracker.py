"""Pull South Boise Village cases from the City of Boise Development Tracker and group them by project.

Usage: python3 tracker.py OUT.json [--neighborhood "South Boise Village"]
"""
import json, sys, datetime as dt
import requests

URL = "https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Development_Tracker_Open_Data/FeatureServer/0/query"


def day(ms):
    if not ms:
        return None
    if isinstance(ms, str):  # the city sometimes sends dates as text, e.g. "2026-11-17" or "11/17/2026 10:00:00 AM"
        text = ms.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            for part in (text, text.split("T")[0].split(" ")[0]):
                try:
                    return dt.datetime.strptime(part, fmt).date().isoformat()
                except ValueError:
                    pass
        return None
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date().isoformat()


def main():
    out = sys.argv[1]
    hood = sys.argv[sys.argv.index("--neighborhood") + 1] if "--neighborhood" in sys.argv else "South Boise Village"
    r = requests.get(URL, params={
        "where": f"NeighborhoodAssociationName='{hood}'", "outFields": "*", "returnGeometry": "true",
        "outSR": "4326", "orderByFields": "AddToTrackerDate DESC", "f": "json"}, timeout=60)
    r.raise_for_status()
    feats = r.json()["features"]
    projects = {}
    for f in feats:
        a = f["attributes"]
        pid = a["ParentRecordID"] or a["RecordID"]
        rec = {"record_id": a["RecordID"], "type": a["RecordType"], "status": a["Status"],
               "address": a["PropertyAddress"], "description": a["Description"], "added": day(a["AddToTrackerDate"]),
               "next_hearing": day(a["NextHearingDate"]), "hearing_body": a["HearingBody"],
               "review_authority": a["ReviewAuthority"], "url": a["Website"]}
        p = projects.setdefault(pid, {"project_id": pid, "records": [], "centroid": None})
        if a["RecordID"] == pid:
            p.update(address=a["PropertyAddress"], description=a["Description"], status=a["Status"], added=day(a["AddToTrackerDate"]), url=a["Website"],
                     record_id=a["RecordID"], next_hearing=day(a["NextHearingDate"]), hearing_body=a["HearingBody"])
        else:
            p["records"].append(rec)
        ring = (f.get("geometry") or {}).get("rings", [[]])[0]
        if ring and not p["centroid"]:
            p["centroid"] = [sum(x for x, _ in ring) / len(ring), sum(y for _, y in ring) / len(ring)]
    for p in projects.values():
        p.setdefault("address", p["records"][0]["address"] if p["records"] else None)
        p.setdefault("status", None)
        p["last_activity"] = max([p.get("added") or ""] + [r["added"] or "" for r in p["records"]])
    res = sorted(projects.values(), key=lambda p: p["last_activity"], reverse=True)
    json.dump({"neighborhood": hood, "pulled": dt.date.today().isoformat(), "projects": res}, open(out, "w"), indent=2)
    for p in res:
        print(p["project_id"], "|", p.get("status"), "|", p.get("address"), "|", p.get("description"), "|", [r["record_id"] for r in p["records"]])


if __name__ == "__main__":
    main()
