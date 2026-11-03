"""Apply the day's city changes to data/projects.json automatically, by fixed rules. Called from update.py.

Nothing here needs a person. The rules are deliberately simple and factual:
  * New projects on the tracker are added with the details the city publishes (address, description, zoning,
    lot size, ADU size, applications) plus their drawings and notice area when posted.
  * Existing projects only change when the city posts something new about them: a status change, a new record,
    a new document, a new appeal period or hearing date. Hand-written text is otherwise left alone.
  * Drawings: the newest elevation / rendering / plan set (or, failing that, site plan or plat) is rendered with
    redact.py, which stamps the City of Boise source and blacks out phone numbers and emails (set the environment
    variable SBV_REDACT_CONTACTS=false to turn that off).
  * Notice areas come from the city's "NOTICING RADIUS MAP" documents (sbvmap.py notice).
  * Projects whose records are all withdrawn/expired/denied, or approved projects 30 days past their appeal
    period, move to "inactive".
Every change is written to the report's change log.
"""
import datetime as dt
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGES = os.path.join(HERE, "images")
DOWNLOADS = os.path.join(HERE, "data", "cache", "downloads")
TODAY = dt.date.today()

PREFIX = {"CZC": "Zoning certificate", "SUB": "Subdivision", "CVA": "Variance", "DRH": "Design review",
          "DRM": "Design review", "CUP": "Conditional use permit", "CAR": "Rezone", "CPA": "Comprehensive plan amendment",
          "PUD": "Planned development", "ROS": "Record of survey", "AWS": "Assured water supply",
          "NBR": "Neighborhood meeting list", "PLN": "Planning project", "CFH": "Floodplain permit",
          "CAA": "Annexation", "MLD": "Minor land division", "DEM": "Demolition", "BLD": "Building permit"}
DONE = re.compile(r"expired|withdrawn|void|denied|cancel|closed|not needed", re.I)
APPROVED = re.compile(r"approved|issued|entitled|recorded|finaled", re.I)
RETURNED = re.compile(r"returned", re.I)
PENDING = re.compile(r"pending application|awaiting application|application submittal", re.I)
DRAWING = re.compile(r"ELEV|RENDER|PLAN SET|ARCHITECT|BUILDING PLANS|DRAWINGS|PERMIT PLANS", re.I)
SITEPLAN = re.compile(r"SITE PLAN|PLAT\b|PRELIMINARY PLAT|LAYOUT", re.I)
SKIP_DOC = re.compile(r"NOTICING RADIUS|NOTICE|RECEIPT|APPLICATION$|COMMENTS|PHOTO|LEGAL INTEREST|TRANSMITTAL", re.I)


# ---------------------------------------------------------------- small helpers
def mdy(s):
    """'10/23/2026' -> date"""
    try:
        m, d, y = s.split("/")
        return dt.date(int(y), int(m), int(d))
    except Exception:
        return None


def nice(d):
    return d.strftime("%b %-d, %Y") if d else ""


def label(rid):
    return PREFIX.get(rid[:3], "Application")


def doc_name(entry):
    return entry.split(" | ")[0]


def doc_date(entry):
    return mdy(entry.split(" | ")[-1])


def title_addr(a):
    a = re.sub(r",.*$", "", a or "").strip()
    return " ".join(w if w in ("N", "S", "E", "W") or w[:1].isdigit() else w.capitalize() for w in a.split())


def lot_addr(a):
    return re.sub(r"\s+", " ", re.sub(r",.*$", "", a or "")).strip().upper()


def log(data, p, text, report):
    data.setdefault("changelog", []).append({"date": TODAY.isoformat(), "project": p["id"], "address": p["address"], "change": text})
    report.append(f"UPDATED       {p['address']}: {text}")


def set_flag(p, ftype, status, label_, detail, record, deadline=None, key=None):
    """Add or update one automatic flag (hand-written flags of other types are left alone)."""
    flags = p.setdefault("flags", [])
    key = key or f"{ftype}:{record}"
    for f in flags:
        if f.get("key") == key or (f.get("type") == ftype and f.get("record") == record):
            f.update(status=status, label=label_, detail=detail, record=record, key=key)
            if deadline:
                f["deadline"] = deadline
            elif "deadline" in f and status != "open":
                pass
            return
    f = {"type": ftype, "status": status, "label": label_, "detail": detail, "record": record, "key": key, "auto": True}
    if deadline:
        f["deadline"] = deadline
    flags.append(f)


def set_timeline(p, step, note, flag=None):
    t = p.setdefault("timeline", {"step": 0, "dates": {}})
    t["step"] = step
    t["flag"] = flag
    t["note"] = note
    t.setdefault("dates", {})[str(step)] = TODAY.isoformat()


def more(rec):
    return (rec or {}).get("more_details_text") or ""


def detail(rec, key, pattern=r"(.+?)(?=\s+[A-Z][\w /()?]+:|$)"):
    m = re.search(re.escape(key) + r":\s*" + pattern, more(rec))
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------- drawings and notice areas
def download(run, rid, name):
    out = os.path.join(DOWNLOADS, rid)
    os.makedirs(out, exist_ok=True)
    run("aca.py", rid, out, "--match", "^" + re.escape(name) + r"(\s|$)", quiet=True)
    rec = json.load(open(os.path.join(out, "record.json")))
    for d in rec.get("documents", []):
        if d.get("file") and d["name"] == name:
            return d["file"]
    return None


def pages_with(pdf, words, limit):
    try:
        import pdfplumber
        with pdfplumber.open(pdf) as doc:
            hits = [i + 1 for i, pg in enumerate(doc.pages) if re.search(words, pg.extract_text() or "", re.I)]
            n = len(doc.pages)
    except Exception:
        return [1]
    return (hits or [1])[:limit] if n > 1 else [1]


def page_width_in(pdf, page):
    try:
        from pypdf import PdfReader
        pg = PdfReader(pdf).pages[page - 1]
        box = pg.mediabox
        w = float(box.height if pg.get("/Rotate", 0) in (90, 270) else box.width)
        return w / 72
    except Exception:
        return 17


def render(run, pdf, page, out, rid):
    dpi = max(100, min(220, int(3600 / page_width_in(pdf, page))))
    args = [pdf, str(page), out, "--record", rid, "--retrieved", TODAY.isoformat(), "--dpi", str(dpi)]
    if os.environ.get("SBV_REDACT_CONTACTS", "true").lower() == "false":
        args.append("--keep-contacts")
    run("redact.py", *args, quiet=True)


def refresh_drawings(p, candidates, run, data, report):
    """candidates: [(rid, entry)] of drawing documents. Uses the newest elevation set, else the newest site plan."""
    elev = [c for c in candidates if DRAWING.search(doc_name(c[1])) and not SKIP_DOC.search(doc_name(c[1]))]
    site = [c for c in candidates if SITEPLAN.search(doc_name(c[1])) and not SKIP_DOC.search(doc_name(c[1]))]
    newest = lambda cs: max(cs, key=lambda c: doc_date(c[1]) or dt.date.min) if cs else None
    picks = []
    e, s_ = newest(elev), newest(site)
    for kind, c, words, limit in (("Elevations", e, r"ELEVATION|RENDER", 2), ("Site plan", s_, r"SITE PLAN|PLAT", 1)):
        if not c:
            continue
        rid, entry = c
        name, up = doc_name(entry), entry.split(" | ")[-1]
        try:
            pdf = download(run, rid, name)
        except RuntimeError as err:
            report.append(f"WARNING       could not download {rid} {name}: {str(err).splitlines()[-1]}")
            continue
        if not pdf or not pdf.lower().endswith(".pdf"):
            continue
        for n, page in enumerate(pages_with(pdf, words, limit), 1):
            slug = re.sub(r"[^a-z0-9]+", "_", f"{p['id']}_{kind}_{n}".lower())
            out = os.path.join(IMAGES, slug + ".jpg")
            try:
                render(run, pdf, page, out, rid)
            except RuntimeError as err:
                report.append(f"WARNING       could not render {name} page {page}: {str(err).splitlines()[-1]}")
                continue
            picks.append({"file": os.path.basename(out), "kind": "Elevations" if kind == "Elevations" else ("Plat" if "PLAT" in name.upper() else "Site plan"),
                          "caption": f"{name.split(' - ', 1)[-1].title()}, uploaded {up} ({rid})" + ("" if kind == "Elevations" or e else " (no elevations filed)"),
                          "source": {"record": rid, "document": name, "uploaded": up, "page": page,
                                     "retrieved": TODAY.isoformat(), "redacted": os.environ.get("SBV_REDACT_CONTACTS", "true").lower() != "false"}})
    if picks:
        old = {i["file"] for i in p.get("images", [])}
        p["images"] = picks
        for f in old - {i["file"] for i in picks}:
            try:
                os.remove(os.path.join(IMAGES, f))
            except OSError:
                pass
        log(data, p, f"Drawings updated from {', '.join(sorted({i['source']['document'] for i in picks}))}.", report)


def refresh_notice(p, rid, entry, run, data, report):
    name = doc_name(entry)
    try:
        pdf = download(run, rid, name)
        out = run("sbvmap.py", "notice", pdf, (p.get("lot_addresses") or [p["address"].upper()])[0], quiet=True)
        addresses = json.loads(out.strip().splitlines()[-1])
    except Exception as err:
        report.append(f"WARNING       notice map for {p['address']} not read automatically: {str(err).splitlines()[-1][:160]}")
        return
    if not addresses:
        return
    kind = "Hearing notice" if rid[:3] in ("CVA", "SUB", "CUP", "CAR", "PUD", "CPA") else "Public notice"
    p["notice"] = {"kind": kind, "record": rid, "document": name, "uploaded": entry.split(" | ")[-1], "addresses": addresses}
    log(data, p, f"Notice area added: {len(addresses)} properties notified (city noticing radius map, {rid}).", report)


# ---------------------------------------------------------------- status rules
def apply_status(p, rid, status, rec, data, report, quiet=False):
    """Update stage, timeline, flags and next step for a record whose status changed (or a new project)."""
    lab = label(rid)
    is_primary = rid == p.get("primary_app") or (rid[:3] not in ("NBR", "AWS", "ROS") and not p.get("primary_app"))
    end = mdy(appeal_end_of(rec) or "")
    for a in p.setdefault("applications", []):
        if a["id"] == rid and a.get("type", "").startswith("Appeal") is False:
            a["status"] = status
    if rid[:3] == "CVA":
        st = "past" if (DONE.search(status) or APPROVED.search(status)) else "upcoming"
        set_flag(p, "variance", st, f"Variance {'requested' if st == 'upcoming' else status.lower()}",
                 f"A variance (permission to depart from a zoning standard) is part of this project. City status: {status}.", rid)
    if not is_primary:
        return
    if DONE.search(status):
        p.update(stage=f"{lab} {status.lower()}", stage_tone="early", next_step=f"City status: {status}.")
    elif APPROVED.search(status):
        if end and end >= TODAY:
            p.update(stage=f"{lab} approved", stage_tone="decision",
                     next_step=f"Approved. Anyone may appeal until {nice(end)}; building permits follow after that.")
            set_timeline(p, 4, f"Approved; appeal period ends {end.strftime('%b %-d')}")
            set_flag(p, "appeal_window", "open", "Appeal window open",
                     f"The city approved this {lab.lower()}. Anyone may appeal the decision by {nice(end)} (the city's notice says fees apply).",
                     rid, deadline=end.isoformat())
        else:
            p.update(stage=f"{lab} approved", stage_tone="decision", next_step="Approved. Building permits are next.")
            set_timeline(p, 5, "Approved" + (f"; appeal period ended {end.strftime('%b %-d')}" if end else ""))
    elif RETURNED.search(status):
        p.update(stage=f"{lab} returned to applicant", stage_tone="attention",
                 next_step="The city returned the application for changes; it must be resubmitted.")
        set_timeline(p, 2, "Returned to applicant for changes", flag="returned")
    elif PENDING.search(status):
        p.update(stage="Awaiting applications", stage_tone="early", next_step="Applications have not been filed yet.")
        set_timeline(p, 0, "Concept review held; applications not yet filed")
    else:
        p.update(stage=f"{lab} in review", stage_tone="review", next_step=f"City review under way (status: {status}).")
        set_timeline(p, 2 if "review" in status.lower() else 1, f"{lab} {status.lower()}")
    if not quiet:
        log(data, p, f"{rid} ({lab.lower()}) status is now {status}.", report)


def appeal_end_of(rec):
    m = re.search(r"Appeal Period End Date:\s*(\d{2}/\d{2}/\d{4})", more(rec))
    return m.group(1) if m else None


def apply_document(p, rid, entry, data, report, run, drawing_queue):
    name = doc_name(entry).upper()
    if "APPEAL" in name:
        p.update(stage="Approval under appeal", stage_tone="attention",
                 next_step="The decision was appealed. The Hearing Examiner will hold a public hearing; written testimony can be submitted before it.")
        set_timeline(p, 4, "Decision appealed; hearing to be scheduled", flag="appealed")
        set_flag(p, "appeal", "upcoming", "Appeal filed: public hearing coming",
                 f"An appeal was filed ({doc_name(entry)}). The Hearing Examiner will hold a public hearing.", rid)
        for f in p.get("flags", []):
            if f.get("type") == "appeal_window":
                f["status"] = "past"
        log(data, p, f"Appeal filed on {rid}.", report)
    elif "NOTICING RADIUS" in name:
        refresh_notice(p, rid, entry, run, data, report)
    elif re.search(r"LEGAL NOTICE|HEARING", name) and re.search(r"HE_|HEARING|P&Z|PZ|COUNCIL|COMMISSION", name):
        set_flag(p, "hearing", "upcoming", "Public hearing noticed",
                 f"The city posted a hearing notice ({doc_name(entry)}). Testimony can be given in writing or at the hearing.", rid)
        log(data, p, f"Hearing notice posted on {rid}.", report)
    if DRAWING.search(name) or SITEPLAN.search(name):
        drawing_queue.append((rid, entry))


def record_flags(p, rid, rtype, status):
    """Flags implied by a record's kind."""
    t, pre = (rtype or "").lower(), rid[:3]
    st = "past" if DONE.search(status or "") else ("info" if APPROVED.search(status or "") else "upcoming")
    if pre == "CVA" or "variance" in t:
        set_flag(p, "variance", st if st != "info" else "past", "Variance requested" if st == "upcoming" else f"Variance {(status or '').lower()}",
                 f"A variance (permission to depart from a zoning standard) is part of this project ({rid}). City status: {status or 'received'}.", rid)
    if pre in ("SUB", "MLD") or "subdivision" in t or "land division" in t:
        set_flag(p, "subdivision", st, "New lots (subdivision)", f"The property is being divided into new lots ({rid}).", rid)
    if pre in ("DRH", "DRM") or "design review" in t:
        set_flag(p, "design_review", st, "Design review", f"Design review application {rid}.", rid)
    if "non-conforming" in t or "nonconforming" in t:
        set_flag(p, "nonconforming", st, "Nonconforming use or structure",
                 f"Application {rid} asks to establish an existing use or structure as legally nonconforming.", rid)
    if "demolition" in t or pre == "DEM":
        set_flag(p, "demolition", st, "Demolition", f"Demolition application {rid}.", rid)
    if pre == "NBR":
        set_flag(p, "neighborhood_meeting", "past" if APPROVED.search(status or "") or "complete" in (status or "").lower() else "upcoming",
                 "Neighborhood meeting", f"A neighborhood meeting is part of this application ({rid}).", rid)


# ---------------------------------------------------------------- new projects
CONCEPT_HEADS = ["Vision/Project Description", "Number and Types of Units", "Access/Parking Information"]


def concept_review(run, recs):
    """Read the city's Concept Review Summary (fixed format) for the project vision, units and parking."""
    best = None
    for rid, r in recs.items():
        for d in r.get("documents", []):
            if d["cells"][0].upper().startswith("PDS-CONCEPT REVIEW SUMMARY"):
                when = mdy(d["cells"][-1]) or dt.date.min
                if best is None or when > best[2]:
                    best = (rid, d["cells"][0], when)
    if not best:
        return {}
    try:
        pdf = download(run, best[0], best[1])
        import pdfplumber
        with pdfplumber.open(pdf) as doc:
            text = "\n".join(pg.extract_text() or "" for pg in doc.pages[:2])
    except Exception:
        return {}
    out = {}
    for i, h in enumerate(CONCEPT_HEADS):
        m = re.search(re.escape(h) + r"\s*(.+?)(?=" + "|".join(re.escape(x) for x in CONCEPT_HEADS[i + 1:] + ["Page 1 of", "Planner Notes"]) + r"|$)", text, re.S)
        if m:
            out[h] = re.sub(r"\s+", " ", m.group(1)).strip()
    return out


def brief(text, limit=200):
    """First sentences of a city text, up to about `limit` characters."""
    if not text:
        return text
    out = ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if out and len(out) + len(sent) > limit:
            break
        out = (out + " " + sent).strip()
    return out[:limit + 40]


def dedupe_flags(p):
    """One flag per kind for demolition / design review / lot split, preferring the one tied to a real application."""
    seen, out = {}, []
    for f in sorted(p.get("flags", []), key=lambda f: "-desc:" in (f.get("key") or "")):
        k = f.get("type") if f.get("type") in ("demolition", "design_review", "subdivision", "variance", "waiver") else id(f)
        if k in seen:
            continue
        seen[k] = True
        out.append(f)
    p["flags"] = out


def description_flags(p, desc, rid):
    d = (desc or "").lower()
    if re.search(r"\bdemo(lish\w*|lition)?\b", d):
        set_flag(p, "demolition", "upcoming", "Demolition", "The project includes demolishing an existing building.", rid, key=f"demolition-desc:{rid}")
    if re.search(r"split (the|this|a|our)? ?lot|lot split|re-?establish\w* (the )?original lot line", d):
        set_flag(p, "subdivision", "upcoming", "Lot split", "The project would divide the property into separate lots.", rid, key=f"split-desc:{rid}")
    if "small lot" in d:
        set_flag(p, "design_review", "upcoming", "Small-lot design review",
                 "Residential small lots go through the city's small-lot design review.", rid, key=f"smalllot-desc:{rid}")
    m = re.search(r"([^.]*\bwaiver\b[^.]*\.)", desc or "", re.I)
    if m:
        set_flag(p, "waiver", "upcoming", "Waiver requested", m.group(1).strip(), rid, key=f"waiver-desc:{rid}")
    if "variance" in d:
        set_flag(p, "variance", "upcoming", "Variance requested", "The project description mentions a variance.", rid, key=f"variance-desc:{rid}")

def kind_of(desc, rids):
    d = (desc or "").lower()
    if re.search(r"split (the|this|a|our)? ?lot|lot split|land division|re-?establish\w* (the )?original lot", d):
        return "Lot split + duplexes" if "duplex" in d else ("Lot split + ADU" if "adu" in d else "Lot split")
    if "small lot" in d:
        return "Small lots + ADUs" if "adu" in d else "Small lots"
    if "townho" in d or "attached" in d:
        return "Attached homes"
    if "duplex" in d or "triplex" in d or "fourplex" in d:
        return "Multi-unit homes"
    if "adu" in d and ("lot" in d or "subdiv" in d):
        return "Small lots + ADUs" if "small" in d else "Subdivision + homes"
    if "adu" in d or "accessory dwelling" in d:
        return "ADU"
    if any(r[:3] == "SUB" for r in rids) or "subdiv" in d:
        return "Subdivision"
    if "land division" in d or "lot split" in d:
        return "Lot split"
    if any(r[:3] == "CVA" for r in rids) or "variance" in d:
        return "Variance"
    if any(r[:3] == "CUP" for r in rids):
        return "Conditional use"
    return (desc or "Project").split(".")[0][:40] or "Project"


def new_project(pid, t, data, fetch_record, fetch_related, run, report):
    address = title_addr(t.get("address"))
    p = {"id": pid, "address": address, "name": (t.get("description") or "Planning project").strip().rstrip("."),
         "kind": "", "summary": "", "stage": "", "stage_tone": "early", "next_step": "",
         "filed": t.get("added") or TODAY.isoformat(), "last_activity": t.get("last_activity") or TODAY.isoformat(),
         "team": "Not shown", "first_seen": TODAY.isoformat(), "auto": True,
         "attributes": {}, "applications": [], "images": [], "flags": [],
         "lot_addresses": [lot_addr(t.get("address"))], "timeline": {"step": 0, "dates": {}, "flag": None, "note": ""}}
    recs = {}
    parent = fetch_record(pid)
    if parent:
        recs[pid] = parent
    for c in t.get("records", []):
        r = fetch_record(c["record_id"])
        if r:
            recs[c["record_id"]] = r
    try:
        for r in fetch_related(pid, p["lot_addresses"][0], p["filed"]):
            if r["record_id"] not in recs and r["record_id"][:3] not in ("ELE", "MEC", "PLM"):
                rr = fetch_record(r["record_id"])
                if rr:
                    recs[r["record_id"]] = rr
    except RuntimeError:
        pass
    for rid, r in recs.items():
        if r.get("detail_url"):
            data.setdefault("record_urls", {})[rid] = r["detail_url"]
    children = [rid for rid in recs if rid != pid]
    main = next((r for r in children if r[:3] in ("SUB", "CZC", "CUP", "CVA", "CAR", "PUD", "DRH") and not DONE.search(recs[r].get("status") or "")), None)
    p["primary_app"] = main or pid
    desc = (parent or {}).get("project_description") or t.get("description") or ""
    desc = desc.strip()
    if desc.upper().startswith(p["lot_addresses"][0]):
        desc = desc[len(p["lot_addresses"][0]):].lstrip(" -:")
    desc = re.sub(r"^.*?\s-\s", "", desc) if " - " in desc[:60] else desc
    cr = concept_review(run, recs)
    vision = cr.get("Vision/Project Description")
    text = vision or desc
    p["kind"] = kind_of(" ".join(x for x in [t.get("description"), vision, desc] if x), list(recs))
    if not t.get("description"):
        p["name"] = p["kind"] if p["kind"] != "Project" else (brief(text, 70) or "Planning project")
    p["summary"] = (text[0].upper() + text[1:] if text else "Planning project") + ("" if text.endswith(".") else ".") + \
        " Added automatically from the City of Boise's case records; see the case file for full details."
    src = recs.get(main) or parent or {}
    zoning = detail(parent, "Zoning District", r"([A-Z0-9-]+)") or detail(src, "Zoning District", r"([A-Z0-9-]+)")
    size = detail(src, "Size of Property", r"([\d.]+)") or detail(parent, "Size of Property", r"([\d.]+)")
    adu = detail(src, "Gross square footage of proposed ADU", r"([\d,]+)")
    beds = detail(src, "How many bedrooms are proposed?", r"(\d+)")
    house = detail(src, "Gross square footage of existing or primary home", r"([\d,]+)")
    p["attributes"] = {
        "Zoning": zoning or "Not shown",
        "Lot": f"{size} ac" if size else "Not shown",
        "Units": brief(cr.get("Number and Types of Units")) or "Not shown",
        "Size": ", ".join(x for x in [f"{adu} SF ADU" if adu else "", f"{beds} bedrooms" if beds else "",
                                      f"existing home {house} SF" if house else ""] if x) or "Not shown",
        "Height": "Not shown", "Setbacks": "Not shown",
        "Parking": brief(cr.get("Access/Parking Information")) or "Not shown", "Access": "Not shown"}
    description_flags(p, " ".join([t.get("description") or "", vision or "", cr.get("Access/Parking Information") or ""]), pid)
    for rid in children:
        rtype = label(rid)
        if any(d["cells"][0].upper().startswith("PDS-DEMOLITION") for d in recs[rid].get("documents", [])):
            rtype = "Demolition permit"
        p["applications"].append({"id": rid, "type": rtype, "status": recs[rid].get("status") or ""})
        record_flags(p, rid, rtype, recs[rid].get("status"))
    primary = p["primary_app"]
    apply_status(p, primary, (recs.get(primary) or {}).get("status") or t.get("status") or "Received", recs.get(primary), data, report, quiet=True)
    queue, notice = [], None
    for rid, r in recs.items():
        for d in r.get("documents", []):
            entry = " | ".join([d["cells"][0], d["cells"][-1]])
            nm = d["cells"][0].upper()
            if "APPEAL" in nm:
                apply_document(p, rid, entry, data, [], run, [])
            if "NOTICING RADIUS" in nm and (notice is None or (doc_date(entry) or dt.date.min) > (doc_date(notice[1]) or dt.date.min)):
                notice = (rid, entry)
            if DRAWING.search(nm) or SITEPLAN.search(nm):
                queue.append((rid, entry))
    dedupe_flags(p)
    data["projects"].append(p)
    log(data, p, f"New project added automatically: {p['name']}.", report)
    if queue:
        refresh_drawings(p, queue, run, data, report)
    if notice:
        refresh_notice(p, notice[0], notice[1], run, data, report)
    return recs


# ---------------------------------------------------------------- daily upkeep
def upkeep(p, data, report, on_tracker, now):
    """Time-based changes: appeal windows closing, approved projects retiring."""
    for f in p.get("flags", []):
        dl = f.get("deadline")
        if f.get("status") == "open" and dl and dt.date.fromisoformat(dl) < TODAY:
            f["status"] = "past"
            if f.get("type") == "appeal_window":
                if not any(g.get("type") == "appeal" and g.get("status") == "upcoming" for g in p["flags"]):
                    p.update(stage_tone="decision",
                             next_step=f"Approved; the appeal period ended {nice(dt.date.fromisoformat(dl))} with no appeal posted. Building permits are next.")
                    set_timeline(p, 5, f"Approved; appeal period ended {dt.date.fromisoformat(dl).strftime('%b %-d')}")
                    log(data, p, "Appeal period ended with no appeal posted.", report)
            elif f.get("type") == "hearing":
                log(data, p, "Hearing date passed.", report)


def retire(data, report, now):
    keep = []
    for p in data["projects"]:
        rids = [p["id"]] + [a["id"] for a in p.get("applications", [])]
        statuses = [now[r]["status"] for r in rids if r in now and now[r].get("status")]
        reason = None
        if statuses and all(DONE.search(s) for s in statuses):
            reason = f"City records show {statuses[0].lower()}."
        t = p.get("timeline") or {}
        approved_on = t.get("dates", {}).get("5")
        if t.get("step") == 5 and approved_on and (TODAY - dt.date.fromisoformat(approved_on)).days > 30 \
                and not any(f.get("status") in ("open", "upcoming") for f in p.get("flags", []) if f.get("type") in ("appeal", "hearing")):
            reason = f"Approved {nice(dt.date.fromisoformat(approved_on))}; no appeal."
        if reason:
            data.setdefault("inactive", []).append({"id": p["id"], "address": p["address"], "note": f"{p.get('name', '')}. {reason}"})
            log(data, p, f"Moved to inactive: {reason}", report)
        else:
            keep.append(p)
    data["projects"] = keep


# ---------------------------------------------------------------- entry point
def apply(data, state, report, fetch_record, fetch_related, run):
    if state.get("first_run"):
        return
    before, now, recs, tracker = state["before"], state["now"], state["records"], state["tracker"]
    os.makedirs(DOWNLOADS, exist_ok=True)
    by_id = {p["id"]: p for p in data["projects"]}
    known = set(by_id) | {x["id"] for x in data.get("inactive", [])}

    # existing projects: react to what changed
    for p in data["projects"]:
        queue = []
        rids = {r for r, s in now.items() if s.get("project") == p["id"]}
        app_ids = {a["id"] for a in p.get("applications", [])}
        latest = None
        for rid in sorted(rids):
            cur, old = now[rid], before.get(rid)
            rec = recs.get(rid)
            if rid != p["id"] and rid not in app_ids and old is None and not DONE.search(cur.get("status") or ""):
                rtype = cur.get("type") or label(rid)
                p.setdefault("applications", []).append({"id": rid, "type": rtype, "status": cur.get("status") or ""})
                record_flags(p, rid, rtype, cur.get("status"))
                log(data, p, f"New application filed: {rid} ({rtype.lower()}).", report)
            if old is None:
                continue
            if cur.get("status") != old.get("status") and cur.get("status"):
                apply_status(p, rid, cur["status"], rec, data, report)
                record_flags(p, rid, label(rid), cur["status"])
            elif cur.get("appeal_end") and cur.get("appeal_end") != old.get("appeal_end") and APPROVED.search(cur.get("status") or ""):
                apply_status(p, rid, cur["status"], rec, data, report)
            for entry in cur.get("documents", []):
                d = doc_date(entry)
                if d and (latest is None or d > latest):
                    latest = d
                if entry not in old.get("documents", []):
                    apply_document(p, rid, entry, data, report, run, queue)
        if latest and latest.isoformat() > (p.get("last_activity") or ""):
            p["last_activity"] = latest.isoformat()
        if queue:
            # include every drawing on the property so the newest set wins
            allc = [(r, e) for r in rids for e in now[r].get("documents", []) if DRAWING.search(doc_name(e)) or SITEPLAN.search(doc_name(e))]
            refresh_drawings(p, allc, run, data, report)
        upkeep(p, data, report, tracker, now)
        dedupe_flags(p)

    # hearing dates published on the tracker
    for pid, t in tracker.items():
        p = by_id.get(pid)
        if not p:
            continue
        for r in [t] + t.get("records", []):
            nh, body = r.get("next_hearing"), r.get("hearing_body")
            if nh and nh >= TODAY.isoformat():
                rid = r.get("record_id") or pid
                existing = next((f for f in p.get("flags", []) if f.get("type") == "hearing" and f.get("deadline") == nh), None)
                if not existing:
                    set_flag(p, "hearing", "open", f"Public hearing {dt.date.fromisoformat(nh).strftime('%b %-d')}",
                             f"{body or 'A public body'} hearing on {nice(dt.date.fromisoformat(nh))}. Testimony can be given in writing beforehand or at the hearing.",
                             rid, deadline=nh, key=f"hearing:{rid}")
                    p.update(next_step=f"Public hearing before {body or 'the city'} on {nice(dt.date.fromisoformat(nh))}.")
                    set_timeline(p, 3, f"Hearing {dt.date.fromisoformat(nh).strftime('%b %-d')}")
                    log(data, p, f"Public hearing scheduled for {nice(dt.date.fromisoformat(nh))} ({body or 'city'}).", report)

    # brand-new projects
    for pid, t in tracker.items():
        if pid in known:
            continue
        try:
            new_recs = new_project(pid, t, data, fetch_record, fetch_related, run, report)
            for rid, r in new_recs.items():
                docs = [" | ".join([d["cells"][0], d["cells"][-1]]) for d in r.get("documents", [])]
                now[rid] = {"status": r.get("status"), "documents": docs, "appeal_end": appeal_end_of(r),
                            "url": r.get("detail_url"), "project": pid}
        except Exception as err:
            report.append(f"WARNING       could not add new project {pid}: {str(err).splitlines()[-1][:200]}")

    retire(data, report, now)
    data["projects"].sort(key=lambda p: p.get("last_activity") or "", reverse=True)
    cutoff = (TODAY - dt.timedelta(days=60)).isoformat()
    data["changelog"] = [c for c in data.get("changelog", []) if c.get("date", "") >= cutoff]
    # keep the saved state in step with any records fetched for new projects
    cache = os.path.join(HERE, "data", "cache", "documents.json")
    try:
        saved = json.load(open(cache))
        saved.update({k: v for k, v in now.items() if k not in saved})
        json.dump(saved, open(cache, "w"), indent=2, ensure_ascii=False)
    except Exception:
        pass
