"""Build the South Boise Village report page from data/projects.json and an image folder.

Usage: python3 build_report.py DATA.json IMG_DIR OUT.html
Images are embedded as data: URIs so the page is self-contained.
"""
import base64, html, json, os, sys, datetime as dt

TONES = {"early": "Early", "review": "In review", "attention": "Needs resubmittal", "decision": "Decision stage"}


def esc(s):
    return html.escape(str(s or ""))


def fmt_date(s):
    if not s:
        return ""
    d = dt.date.fromisoformat(s)
    return d.strftime("%b %-d, %Y")


STEPS = ["Concept", "Filed", "Review", "Hearing", "Decision", "Approved"]
STEP_HELP = ["Concept review with planning staff", "Applications filed with the city", "City staff and agency review",
             "Public notice, neighborhood meeting or hearing", "Final decision by staff, Hearing Examiner or City Council",
             "Approved; building permits next"]


FLAG_LABELS = {"returned": "Returned", "appealed": "Appealed"}


def short_date(s):
    return dt.date.fromisoformat(s).strftime("%b %-d") if s else ""


def timeline_html(p, compact=False):
    t = p.get("timeline") or {}
    step = int(t.get("step", 0))
    dates = t.get("dates", {})
    tone = esc(p.get("stage_tone", "review"))
    if compact:
        dots = "".join(f'<i class="{"done" if i < step else "now" if i == step else "todo"}" title="{STEPS[i]}"></i>' for i in range(len(STEPS)))
        return f'<span class="mini tone-{tone}" aria-label="Step {step + 1} of {len(STEPS)}: {STEPS[step]}">{dots}</span>'
    items = []
    for i, label in enumerate(STEPS):
        state = "done" if i < step else "now" if i == step else "todo"
        sub = short_date(dates.get(str(i)))
        if i == step and t.get("flag") in FLAG_LABELS:
            sub = FLAG_LABELS[t["flag"]]
        items.append(f'<li class="{state}" title="{esc(STEP_HELP[i])}"><span class="pt"></span><b>{label}</b><small>{esc(sub)}</small></li>')
    note = f'<p class="tl-note"><span class="lbl">Where it stands</span>{esc(t.get("note", ""))}</p>' if t.get("note") else ""
    return f'<div class="tl-band tone-{tone}"><ol class="tl" aria-label="Approval timeline, step {step + 1} of {len(STEPS)}">{"".join(items)}</ol>{note}</div>'


RECORD_URLS = {}
TODAY = [None]
FLAG_STATUS = {"open": ("Open now", 0), "upcoming": ("Coming up", 1), "info": ("Worth a look", 2), "past": ("Closed", 3)}


def flag_when(f):
    if f.get("deadline"):
        dl = dt.date.fromisoformat(f["deadline"])
        left = (dl - TODAY[0]).days if TODAY[0] else None
        tail = "" if left is None else (" · today" if left == 0 else f" · {left} days left" if left > 0 else " · passed")
        return f'Deadline {dl.strftime("%b %-d")}<span class="left" data-deadline="{dl.isoformat()}">{tail}</span>'
    return ""


def flag_chips(p, limit=3):
    fl = sorted(p.get("flags", []), key=lambda f: FLAG_STATUS.get(f["status"], ("", 9))[1])
    fl = [f for f in fl if f["status"] != "past"] or fl
    chips = []
    for f in fl[:limit]:
        extra = f' by {dt.date.fromisoformat(f["deadline"]).strftime("%b %-d")}' if f.get("deadline") and f["status"] == "open" else ""
        chips.append(f'<span class="flag fs-{esc(f["status"])}">{esc(f["label"])}{esc(extra)}</span>')
    return "".join(chips) or '<span class="noflag">None</span>'


def neighbors_html(p):
    fl = sorted(p.get("flags", []), key=lambda f: FLAG_STATUS.get(f["status"], ("", 9))[1])
    if not fl:
        return ""
    items = "".join(
        f'<li class="fs-{esc(f["status"])}"><span class="fstat">{FLAG_STATUS.get(f["status"], ("", 0))[0]}</span>'
        f'<div><strong>{esc(f["label"])}</strong><p>{esc(f["detail"])}</p>'
        f'<small>{" " + flag_when(f) + " · " if flag_when(f) else ""}City case {rec_link(f["record"])}</small></div></li>' for f in fl)
    c = p.get("contact")
    case = p.get("primary_app") or p["id"]
    if c:
        how = (f'Contact the assigned city planner, <strong>{esc(c["planner"])}</strong>: <span class="sel">{esc(c["email"])}</span> · '
               f'<span class="sel">{esc(c["phone"])}</span>. Cite case {esc(case)}. <span class="muted">(Named in the city\'s {esc(c["source"])}.)</span>')
    else:
        how = (f'Contact Boise Planning &amp; Development Services at <span class="sel">208-608-7100</span> and cite case {esc(case)}; '
               'a planner is assigned once applications are filed.')
    return f'''<div class="nbr"><div class="nbr-head"><span class="lbl">For neighbors</span>
      <p>Items in this application that are open to public input or that neighbors often want to review. Flags are not a judgment on the project.</p></div>
      <ul class="nbr-list">{items}</ul>
      <p class="nbr-how"><span class="lbl">How to weigh in</span>{how} Written comments go into the case record; at hearings the city also takes testimony in person or by email.</p></div>'''
MAP = {}


def notice_caption(p):
    nt = p.get("notice") or {}
    m = MAP.get("projects", {}).get(p["id"], {})
    if nt.get("radius_ft") and m.get("notice_count"):
        return (f'<strong>Notice area:</strong> the {m["notice_count"]} parcels within {nt["radius_ft"]} feet of the property, '
                f'per the City of Boise staff report ({esc(nt.get("kind", "hearing notice"))}). '
                f'Source: {rec_link(nt["record"])} · parcels from Ada County parcel data.')
    if nt.get("addresses") and m.get("notice_count"):
        return (f'<strong>Notice area:</strong> the {m["notice_count"]} neighboring parcels the City of Boise selected for mailed '
                f'{esc(nt.get("kind", "notice").lower())}. Source: <a href="{esc(rec_url(nt["record"]))}" target="_blank" rel="noopener">'
                f'{esc(nt["document"])} ↗</a>, City of Boise case file {esc(nt["record"])}'
                f'{", uploaded " + esc(nt["uploaded"]) if nt.get("uploaded") else ""}.')
    return ('<strong>No notice area yet.</strong> The city adds a noticing radius map to an application when it reaches '
            'public notice. It will be drawn here once posted.')


def notice_parcels_svg(m):
    """Every notified property drawn with its own property lines, with its address as a tooltip."""
    return "".join(f'<path class="nt-lot" d="{q["d"]}"><title>{esc(q["address"].title())}</title></path>'
                   for q in m.get("notice_parcels", []))


def minimap_html(p):
    m = MAP.get("projects", {}).get(p["id"])
    if not m:
        return ""
    z = m["zoom"]
    vb = " ".join(str(v) for v in z["viewBox"])
    x0, y0, w, h = z["viewBox"]
    bar = 30.48  # 100 feet in map units (meters)
    bx, by = x0 + w * 0.05, y0 + h * 0.94
    notice = (f'{notice_parcels_svg(m)}<path class="nt-line" d="{m["notice_outline"]}"/>' if m.get("notice") else "")
    return f'''<div class="minimap"><span class="lbl">Lot and notice area</span>
      <svg viewBox="{vb}" role="img" aria-label="Map of the lot at {esc(p["address"])} and its notice area">
        <rect x="{x0}" y="{y0}" width="{w}" height="{h}" class="mm-bg"/>
        <path class="mm-parcels" d="{z["parcels"]}"/>{notice}
        <path class="lot tone-{esc(p["stage_tone"])}" d="{m["lot"]}"/>
        <g class="mm-scale"><line x1="{bx}" y1="{by}" x2="{bx + bar}" y2="{by}"/><text x="{bx + bar + w * 0.015}" y="{by + w * 0.012}" style="font-size:{w * 0.036:.1f}px">100 ft</text></g>
        <g class="mm-north" transform="translate({x0 + w * 0.93} {y0 + h * 0.08})"><path d="M0,{-w*0.03} L{w*0.014},{w*0.012} L0,{w*0.004} L{-w*0.014},{w*0.012}Z"/><text y="{w*0.05}" style="font-size:{w * 0.036:.1f}px">N</text></g>
      </svg>
      <p class="mm-cap">{notice_caption(p)}</p></div>'''


def overview_map(projects):
    if not MAP:
        return ""
    vb = MAP["viewBox"]
    x0, y0, w, h = vb
    notices = "".join(notice_parcels_svg(MAP["projects"][p["id"]]) for p in projects
                      if MAP["projects"].get(p["id"], {}).get("notice"))
    outlines = "".join(f'<path class="nt-line" d="{MAP["projects"][p["id"]]["notice_outline"]}"/>' for p in projects
                       if MAP["projects"].get(p["id"], {}).get("notice"))
    lots, marks = [], []
    for n, p in enumerate(projects, 1):
        m = MAP["projects"].get(p["id"])
        if not m:
            continue
        lots.append(f'<path class="lot tone-{esc(p["stage_tone"])}" d="{m["lot"]}"/>')
        marks.append(f'<a href="#{p["id"].lower()}" class="mk tone-{esc(p["stage_tone"])}" aria-label="{n:02d} {esc(p["address"])}">'
                     f'<circle cx="{m["cx"]}" cy="{m["cy"] - 30}" r="17"/><text x="{m["cx"]}" y="{m["cy"] - 30 + 6}">{n}</text>'
                     f'<line x1="{m["cx"]}" y1="{m["cy"] - 13}" x2="{m["cx"]}" y2="{m["cy"]}"/></a>')
    streets = []
    for st in MAP.get("streets", []):
        if st["n"] < 12:
            continue
        a = st["angle"]
        if a > 60: a -= 180
        streets.append(f'<text class="st" transform="translate({st["x"]} {st["y"]}) rotate({a})">{esc(st["name"])}</text>')
    bar = 152.4
    bx, by = x0 + 30, y0 + h - 30
    key = "".join(f'<li><a href="#{p["id"].lower()}"><b class="kn tone-{esc(p["stage_tone"])}">{n}</b>{esc(p["address"])}</a>'
                  f'<span>{esc(p["stage"])}{" · notice area shown" if MAP["projects"].get(p["id"], {}).get("notice") else ""}</span></li>'
                  for n, p in enumerate(projects, 1))
    return f'''<section class="overview-map" aria-label="Project map">
  <div class="map-frame">
    <svg viewBox="{x0} {y0} {w} {h}" role="img" aria-label="Map of South Boise Village showing project lots and notice areas">
      <defs><pattern id="hatch" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="9" class="hatch"/></pattern></defs>
      <rect x="{x0}" y="{y0}" width="{w}" height="{h}" class="mm-bg"/>
      <path class="parcels" d="{MAP["parcels"]}"/>
      {notices}{outlines}
      <path class="hood" d="{MAP["boundary"]}"/>
      {"".join(streets)}
      {"".join(lots)}{"".join(marks)}
      <g class="mm-scale"><line x1="{bx}" y1="{by}" x2="{bx + bar}" y2="{by}"/><text x="{bx + bar + 10}" y="{by + 6}">500 ft</text></g>
      <g class="mm-north" transform="translate({x0 + w - 50} {y0 + 60})"><path d="M0,-34 L16,14 L0,5 L-16,14Z"/><text y="48">N</text></g>
    </svg>
  </div>
  <div class="map-side">
    <h2>Where the projects are</h2>
    <p>Lots are colored by stage. The hatched areas are the parcels that received mailed notice, each drawn with its own property lines, as published by the City of Boise in each application's noticing radius map or staff report. The dashed line is the South Boise Village neighborhood association boundary.</p>
    <ol class="mapkey">{key}</ol>
    <p class="mapsrc">Parcels and neighborhood boundary: City of Boise open data (Ada County parcels). Notice areas: City of Boise case files, linked on each project below.</p>
  </div>
</section>'''



def recent_html(data):
    """Changes from the last 14 days, newest first, from the change log."""
    today = dt.date.fromisoformat(data["updated"])
    cutoff = (today - dt.timedelta(days=14)).isoformat()
    ids = {p["id"] for p in data["projects"]}
    items = [c for c in data.get("changelog", []) if c.get("date", "") >= cutoff]
    items.sort(key=lambda c: c["date"], reverse=True)
    if not items:
        rows = '<li class="none">No changes in the last two weeks.</li>'
    else:
        rows = "".join(
            f'<li><time>{dt.date.fromisoformat(c["date"]).strftime("%b %-d")}</time>'
            f'<span>{(f"<a href=\"#{c["project"].lower()}\">{esc(c["address"])}</a>" if c["project"] in ids else esc(c["address"]))}: {esc(c["change"])}</span></li>'
            for c in items[:25])
    return (f'<section class="recent" aria-label="Recent changes"><h2>Recent changes</h2>'
            f'<p>Updated automatically every morning from the City of Boise\'s public records.</p><ul>{rows}</ul></section>')


def rec_url(rid):
    return RECORD_URLS.get(rid) or f"https://permits.cityofboise.org/CitizenAccess/Cap/GlobalSearchResults.aspx?QueryText={rid}"


def rec_link(rid, cls="rec"):
    return f'<a class="{cls}" href="{esc(rec_url(rid))}" target="_blank" rel="noopener">{esc(rid)}</a>'


def caption_html(i):
    src = i.get("source") or {}
    if not src:
        return f'<span class="cap">{esc(i["caption"])}</span>'
    ret = src.get("retrieved")
    ret = dt.date.fromisoformat(ret).strftime("%-m/%-d/%Y") if ret else ""
    bits = [f'page {src["page"]}' if src.get("page") and src.get("page") != 1 else "",
            f'uploaded by the city {src["uploaded"]}' if src.get("uploaded") else "",
            f'retrieved {ret}' if ret else "", "contact details redacted" if src.get("redacted") else ""]
    meta = " · ".join(b for b in bits if b)
    return (f'<span class="cap">{esc(i["caption"])}</span>'
            f'<span class="src"><span class="lbl">Source: City of Boise Planning &amp; Development Services website</span>'
            f'<a href="{esc(rec_url(src["record"]))}" target="_blank" rel="noopener">{esc(src["document"])} ↗</a>'
            f'<small>Public document listed under Documents on City of Boise case file {esc(src["record"])} '
            f'(permits.cityofboise.org){" · " + meta if meta else ""}</small></span>')


def img_uri(path):
    with open(path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def project_html(p, img_dir, idx):
    imgs = [i for i in p.get("images", []) if os.path.exists(os.path.join(img_dir, i["file"]))]
    pid = p["id"].lower()
    if imgs:
        lead = imgs[0]
        thumbs = "".join(
            f'<button class="thumb{" on" if n == 0 else ""}" type="button" data-src="{pid}-{n}" aria-label="Show {esc(i["kind"])}">'
            f'<img src="" data-ref="{pid}-{n}" alt="{esc(i["caption"])}"><span>{esc(i["kind"])}</span></button>'
            for n, i in enumerate(imgs))
        figure = (f'<figure class="drawing"><button class="zoom" type="button" aria-label="Enlarge drawing">'
                  f'<img class="main" data-ref="{pid}-0" src="" alt="{esc(lead["caption"])}"></button>'
                  f'<figcaption>{caption_html(lead)}</figcaption>'
                  + (f'<div class="thumbs">{thumbs}</div>' if len(imgs) > 1 else "") + '</figure>')
    else:
        figure = ('<figure class="drawing empty"><div class="nodraw"><strong>No drawings posted yet</strong>'
                  '<span>Plans appear here once the applications are filed.</span></div></figure>')
    has_elev = any(i["kind"] in ("Elevations", "Rendering") for i in imgs)
    attrs = "".join(f'<div class="cell"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in p["attributes"].items())
    apps = "".join(f'<li><code>{rec_link(a["id"])}</code><span>{esc(a["type"])}</span><em>{esc(a["status"])}</em></li>' for a in p.get("applications", []))
    case_url = esc(rec_url(p["id"]))
    return f'''
<article class="sheet" id="{pid}">
  <header class="sheet-head">
    <div class="sheet-no">{idx:02d}</div>
    <div class="sheet-title">
      <p class="eyebrow"><span class="kind">{esc(p["kind"])}</span>{'<span class="new">New this week</span>' if p.get("is_new") else ""}{'' if has_elev else '<span class="noelev">No elevations filed</span>'}</p>
      <h2>{esc(p["address"])}</h2>
      <p class="pname">{esc(p["name"])}</p>
    </div>
    <div class="stage tone-{esc(p["stage_tone"])}"><span class="dot"></span><div><strong>{esc(p["stage"])}</strong><small>{esc("Under appeal" if (p.get("timeline") or {}).get("flag") == "appealed" else TONES.get(p["stage_tone"], ""))}</small></div></div>
  </header>
  {timeline_html(p)}
  {neighbors_html(p)}
  <div class="sheet-body">
    <div class="leftcol">{figure}{minimap_html(p)}</div>
    <aside class="block">
      <p class="summary">{esc(p["summary"])}</p>
      <dl class="grid">{attrs}</dl>
      <div class="next"><span class="lbl">Next step</span><p>{esc(p["next_step"])}</p></div>
      {f'<div class="apps"><span class="lbl">Applications</span><ul>{apps}</ul></div>' if apps else ''}
      <div class="foot">
        <div><span class="lbl">Project</span><code>{esc(p["id"])}</code></div>
        <div><span class="lbl">Filed</span>{fmt_date(p["filed"])}</div>
        <div><span class="lbl">Last activity</span>{fmt_date(p["last_activity"])}</div>
        <div class="team"><span class="lbl">Team</span>{esc(p["team"])}</div>
        <a class="case" href="{case_url}" target="_blank" rel="noopener">Open project case file {esc(p["id"])} ↗</a>
      </div>
    </aside>
  </div>
</article>'''


def build(data, img_dir, map_data=None):
    projects = data["projects"]
    TODAY[0] = dt.date.fromisoformat(data["updated"])
    MAP.clear()
    MAP.update(map_data or {})
    RECORD_URLS.clear()
    RECORD_URLS.update(data.get("record_urls", {}))
    # "New this week": first seen by the agent within 7 days of this update (falls back to a stored is_new flag).
    cutoff = (dt.date.fromisoformat(data["updated"]) - dt.timedelta(days=7)).isoformat()
    for p in projects:
        if p.get("first_seen"):
            p["is_new"] = p["first_seen"] > cutoff
    img_map = {}
    for p in projects:
        for n, i in enumerate(p.get("images", [])):
            path = os.path.join(img_dir, i["file"])
            if os.path.exists(path):
                img_map[f'{p["id"].lower()}-{n}'] = {"src": img_uri(path), "cap": i["caption"], "caphtml": caption_html(i)}
    counts = {}
    for p in projects:
        counts[p["stage_tone"]] = counts.get(p["stage_tone"], 0) + 1
    new_n = sum(1 for p in projects if p.get("is_new"))
    units_note = sum(1 for p in projects if any(i["kind"] == "Elevations" for i in p.get("images", [])))
    index_rows = "".join(
        f'<tr><td><a href="#{p["id"].lower()}">{esc(p["address"])}</a>{" <b class=newtag>New</b>" if p.get("is_new") else ""}</td>'
        f'<td>{esc(p["kind"])}</td><td class="flagcell">{flag_chips(p)}</td><td class="appcell">{rec_link(p.get("primary_app") or p["id"], "applink")}</td><td><div class="stagecell">{timeline_html(p, compact=True)}<span class="pill tone-{esc(p["stage_tone"])}">{esc(p["stage"])}</span></div></td>'
        f'<td class="num">{fmt_date(p["last_activity"])}</td></tr>' for p in projects)
    sheets = "".join(project_html(p, img_dir, n + 1) for n, p in enumerate(projects))
    inactive = "".join(f'<li><code>{esc(x["id"])}</code> {esc(x["address"])}: {esc(x["note"])}</li>' for x in data.get("inactive", []))
    stat = lambda tone: counts.get(tone, 0)
    return TEMPLATE.format(
        open_n=sum(1 for p in projects if any(f["status"] in ("open", "upcoming") and f["type"] in ("appeal_window", "appeal", "hearing", "variance") for f in p.get("flags", []))),
        updated=fmt_date(data["updated"]), n=len(projects), new_n=new_n, elev_n=units_note,
        early=stat("early"), review=stat("review") + stat("attention"), decision=stat("decision"),
        index_rows=index_rows, sheets=sheets, overview=overview_map(projects), recent=recent_html(data), inactive=inactive, hood=esc(data["neighborhood"]),
        img_json=json.dumps(img_map).replace("</", "<\\/"))


TEMPLATE = r'''<title>South Boise Village Projects</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: neighborhood header + index table, then one "drawing sheet" per project — drawing left, title-block grid right. */
:root {{
  --paper: #f6f8f7; --sheet: #ffffff; --ink: #18211f; --muted: #5d6a66; --rule: #cfd8d5; --rule-strong: #8fa19b;
  --accent: #1d5c63; --accent-soft: #e2eeee; --plan: #f2f5f4;
  --early: #6b6f86; --early-bg: #eceef5; --review: #1d5c63; --review-bg: #e2eeee;
  --attention: #a3541b; --attention-bg: #f8eadf; --decision: #4e6b1f; --decision-bg: #e9f0dc; --new: #a3541b;
  --display: "Archivo", "Arial Narrow", "Helvetica Neue", Arial, sans-serif;
  --body: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --paper: #111816; --sheet: #172120; --ink: #e5ecea; --muted: #9aa9a5; --rule: #2c3a37; --rule-strong: #4c5e59;
  --accent: #7cc4c6; --accent-soft: #1b3436; --plan: #eef2f1;
  --early: #b1b5cc; --early-bg: #262a38; --review: #7cc4c6; --review-bg: #1b3436;
  --attention: #f0a56d; --attention-bg: #3a2516; --decision: #b4d07e; --decision-bg: #27321a; --new: #f0a56d; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --paper: #111816; --sheet: #172120; --ink: #e5ecea; --muted: #9aa9a5; --rule: #2c3a37; --rule-strong: #4c5e59;
  --accent: #7cc4c6; --accent-soft: #1b3436; --plan: #eef2f1;
  --early: #b1b5cc; --early-bg: #262a38; --review: #7cc4c6; --review-bg: #1b3436;
  --attention: #f0a56d; --attention-bg: #3a2516; --decision: #b4d07e; --decision-bg: #27321a; --new: #f0a56d; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--paper); color: var(--ink); font: 15px/1.5 var(--body); }}
.wrap {{ max-width: 1240px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 32px 64px; display: grid; gap: 40px; }}
a {{ color: var(--accent); }}
a:focus-visible, button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
code {{ font-family: var(--mono); font-size: .86em; }}
.lbl {{ display: block; font: 600 10.5px/1.2 var(--body); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); margin-bottom: 3px; }}

/* Masthead */
.mast {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 24px 40px; align-items: end; border-bottom: 2px solid var(--ink); padding-bottom: 20px; }}
.homelink {{ margin: 0 0 14px; font-size: 14px; }}
.homelink a {{ display: inline-block; padding: 4px 10px; border: 1px solid var(--accent); border-radius: 3px; color: var(--accent); font-weight: 600; text-decoration: none; }}
.homelink a:hover {{ background: var(--accent-soft); }}
.mast .eyebrow {{ font: 600 12px var(--body); letter-spacing: .12em; text-transform: uppercase; color: var(--accent); margin: 0 0 6px; }}
.mast h1 {{ font: 800 clamp(34px, 6vw, 64px)/.95 var(--display); font-stretch: 72%; letter-spacing: -.01em; margin: 0; text-wrap: balance; text-transform: uppercase; }}
.mast p.lede {{ margin: 12px 0 0; color: var(--muted); max-width: 62ch; }}
.tallies {{ display: grid; grid-template-columns: repeat(5, auto); gap: 0; border: 1px solid var(--rule-strong); }}
.tally {{ padding: 10px 16px; border-left: 1px solid var(--rule); min-width: 92px; }}
.tally:first-child {{ border-left: 0; }}
.tally b {{ display: block; font: 700 30px/1 var(--display); font-stretch: 80%; font-variant-numeric: tabular-nums; }}
.tally span {{ font-size: 12px; color: var(--muted); }}

.notice {{ margin: 14px 0 0; max-width: 78ch; padding: 10px 14px; border: 1px solid var(--attention); border-left-width: 4px; background: var(--attention-bg); color: var(--ink); font-size: 13.5px; line-height: 1.5; border-radius: 2px; }}
.notice strong {{ color: var(--attention); }}

/* Index */
.index {{ overflow-x: auto; }}
.index table {{ width: 100%; border-collapse: collapse; font-size: 14px; min-width: 560px; }}
.index th {{ text-align: left; font: 600 10.5px var(--body); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); padding: 8px 12px; border-bottom: 1px solid var(--rule-strong); }}
.index td {{ padding: 10px 12px; border-bottom: 1px solid var(--rule); vertical-align: middle; }}
.index td a {{ font-weight: 600; text-decoration: none; color: var(--ink); }}
.index td a:hover {{ color: var(--accent); text-decoration: underline; }}
.num {{ font-variant-numeric: tabular-nums; white-space: nowrap; color: var(--muted); }}
.newtag {{ font: 600 10px var(--body); letter-spacing: .08em; text-transform: uppercase; color: var(--new); margin-left: 6px; }}
.pill {{ display: inline-block; padding: 2px 10px; border-radius: 99px; font-size: 12.5px; font-weight: 500; white-space: nowrap; }}
.tone-early {{ --t: var(--early); --tb: var(--early-bg); }} .tone-review {{ --t: var(--review); --tb: var(--review-bg); }}
.tone-attention {{ --t: var(--attention); --tb: var(--attention-bg); }} .tone-decision {{ --t: var(--decision); --tb: var(--decision-bg); }}
.pill {{ color: var(--t); background: var(--tb); }}

/* Sheets */
.sheets {{ display: grid; gap: 36px; }}
.sheet {{ background: var(--sheet); border: 1px solid var(--rule-strong); scroll-margin-top: 16px; }}
.sheet-head {{ display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 18px; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--rule-strong); }}
.sheet-no {{ font: 700 15px var(--mono); color: var(--muted); border: 1px solid var(--rule-strong); border-radius: 50%; width: 44px; height: 44px; display: grid; place-items: center; }}
.sheet-title h2 {{ font: 750 clamp(22px, 3vw, 30px)/1.05 var(--display); font-stretch: 78%; text-transform: uppercase; margin: 2px 0 0; text-wrap: balance; }}
.pname {{ margin: 2px 0 0; color: var(--muted); font-size: 14px; }}
.eyebrow {{ display: flex; flex-wrap: wrap; gap: 6px 12px; margin: 0; font: 600 11px var(--body); letter-spacing: .09em; text-transform: uppercase; }}
.eyebrow .kind {{ color: var(--accent); }} .eyebrow .new {{ color: var(--new); }} .eyebrow .noelev {{ color: var(--muted); }}
.stage {{ display: flex; gap: 10px; align-items: center; padding: 8px 14px; background: var(--tb); color: var(--t); border-radius: 6px; max-width: 260px; }}
.stage .dot {{ width: 10px; height: 10px; border-radius: 50%; background: var(--t); flex: none; }}
.stage strong {{ display: block; font-size: 13.5px; line-height: 1.25; }}
.stage small {{ font-size: 11.5px; opacity: .85; }}
.sheet-body {{ display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(300px, 1fr); }}
.leftcol {{ border-right: 1px solid var(--rule-strong); min-width: 0; display: grid; align-content: start; }}
.drawing {{ margin: 0; padding: 16px; display: grid; gap: 10px; align-content: start; min-width: 0; }}
.zoom {{ all: unset; cursor: zoom-in; display: block; background: var(--plan); border: 1px solid var(--rule); border-radius: 2px; }}
.zoom img {{ display: block; width: 100%; height: auto; aspect-ratio: 3 / 2; object-fit: contain; }}
.drawing figcaption {{ font-size: 12.5px; color: var(--muted); }}
.thumbs {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.thumb {{ all: unset; cursor: pointer; width: 112px; display: grid; gap: 4px; font-size: 11.5px; color: var(--muted); }}
.thumb img {{ width: 112px; aspect-ratio: 3/2; object-fit: contain; background: var(--plan); border: 1px solid var(--rule); }}
.thumb.on img {{ border: 2px solid var(--accent); }}
.thumb.on span {{ color: var(--ink); font-weight: 600; }}
.nodraw {{ aspect-ratio: 3 / 2; display: grid; place-content: center; gap: 4px; text-align: center; border: 1px dashed var(--rule-strong); color: var(--muted); padding: 16px;
  background-image: linear-gradient(var(--rule) 1px, transparent 1px), linear-gradient(90deg, var(--rule) 1px, transparent 1px); background-size: 24px 24px; }}
.nodraw strong {{ color: var(--ink); font-family: var(--display); font-stretch: 85%; font-size: 18px; text-transform: uppercase; }}
.block {{ display: grid; align-content: start; min-width: 0; }}
.summary {{ margin: 0; padding: 16px 18px; border-bottom: 1px solid var(--rule); line-height: 1.55; }}
.grid {{ margin: 0; display: grid; grid-template-columns: 1fr 1fr; }}
.cell {{ padding: 9px 18px 10px; border-bottom: 1px solid var(--rule); min-width: 0; }}
.cell:nth-child(odd) {{ border-right: 1px solid var(--rule); }}
.cell dt {{ font: 600 10.5px/1.2 var(--body); letter-spacing: .09em; text-transform: uppercase; color: var(--muted); }}
.cell dd {{ margin: 3px 0 0; font-size: 13.5px; line-height: 1.4; }}
.next, .apps {{ padding: 12px 18px; border-bottom: 1px solid var(--rule); }}
.next p {{ margin: 0; font-size: 14px; }}
.apps ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }}
.apps li {{ display: grid; grid-template-columns: 104px minmax(0, 1fr) auto; gap: 8px; font-size: 13px; align-items: baseline; }}
.apps em {{ font-style: normal; color: var(--muted); font-size: 12px; text-align: right; }}
.foot {{ display: grid; grid-template-columns: 1fr 1fr 1fr; font-size: 13px; background: var(--accent-soft); }}
.foot > div {{ padding: 10px 18px; border-right: 1px solid var(--rule); font-variant-numeric: tabular-nums; }}
.foot > div:nth-child(3) {{ border-right: 0; }}
.foot .team {{ grid-column: 1 / -1; border-top: 1px solid var(--rule); border-right: 0; }}
.foot .case {{ grid-column: 1 / -1; padding: 10px 18px; border-top: 1px solid var(--rule); font-weight: 600; text-decoration: none; }}
.foot .case:hover {{ text-decoration: underline; }}

/* Recent changes */
.recent h2 {{ font: 750 22px/1.05 var(--display); font-stretch: 78%; text-transform: uppercase; margin: 0 0 4px; }}
.recent > p {{ margin: 0 0 10px; color: var(--muted); font-size: 13.5px; }}
.recent ul {{ list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--rule); }}
.recent li {{ display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--rule); font-size: 14px; }}
.recent li.none {{ display: block; color: var(--muted); }}
.recent time {{ color: var(--muted); font-variant-numeric: tabular-nums; font-size: 13px; }}
.recent a {{ font-weight: 600; color: var(--ink); }}

/* Maps */
.overview-map {{ display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(260px, 1fr); gap: 24px 32px; align-items: start; }}
.map-frame {{ border: 1px solid var(--rule-strong); background: var(--sheet); }}
.map-frame svg {{ display: block; width: 100%; height: auto; max-height: 82vh; }}
.map-side h2 {{ font: 750 26px/1.05 var(--display); font-stretch: 78%; text-transform: uppercase; margin: 0 0 8px; }}
.map-side p {{ margin: 0 0 12px; color: var(--muted); font-size: 14px; max-width: 60ch; }}
.mapkey {{ list-style: none; margin: 0 0 14px; padding: 0; display: grid; border-top: 1px solid var(--rule); }}
.mapkey li {{ display: grid; gap: 1px; padding: 8px 0; border-bottom: 1px solid var(--rule); }}
.mapkey a {{ display: flex; gap: 10px; align-items: center; font-weight: 600; color: var(--ink); text-decoration: none; }}
.mapkey a:hover {{ color: var(--accent); }}
.mapkey span {{ padding-left: 34px; font-size: 13px; color: var(--muted); }}
.kn {{ display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: var(--t); color: var(--sheet); font: 700 12px var(--body); flex: none; }}
.mapsrc {{ font-size: 12px !important; }}
.mm-bg {{ fill: var(--sheet); }}
.parcels, .mm-parcels {{ fill: none; stroke: var(--rule); stroke-width: 1; vector-effect: non-scaling-stroke; }}
.hood {{ fill: none; stroke: var(--ink); stroke-width: 2; stroke-dasharray: 8 5; vector-effect: non-scaling-stroke; }}
.hatch {{ stroke: var(--accent); stroke-width: 2; opacity: .55; }}
.nt-fill {{ fill: url(#hatch); fill: var(--accent-soft); }}
.overview-map .nt-fill {{ fill: url(#hatch); }}
.nt-lot {{ fill: var(--accent-soft); stroke: var(--accent); stroke-width: 1.1; vector-effect: non-scaling-stroke; }}
.overview-map .nt-lot {{ fill: url(#hatch); stroke-width: .8; }}
.nt-lot:hover {{ fill: var(--attention-bg); }}
.nt-line {{ fill: none; stroke: var(--accent); stroke-width: 1.6; stroke-dasharray: 5 3; vector-effect: non-scaling-stroke; }}
.lot {{ fill: var(--t); stroke: var(--sheet); stroke-width: 1; vector-effect: non-scaling-stroke; }}
.mk circle {{ fill: var(--t); stroke: var(--sheet); stroke-width: 3; }}
.mk text {{ fill: var(--sheet); font: 700 19px var(--body); text-anchor: middle; }}
.mk line {{ stroke: var(--t); stroke-width: 2.5; }}
.mk:hover circle, .mk:focus circle {{ stroke: var(--ink); }}
.st {{ font: 500 15px var(--body); fill: var(--muted); text-anchor: middle; paint-order: stroke; stroke: var(--sheet); stroke-width: 4px; letter-spacing: .02em; }}
.mm-scale line {{ stroke: var(--ink); stroke-width: 3; vector-effect: non-scaling-stroke; }}
.mm-scale text, .mm-north text {{ fill: var(--ink); font: 600 16px var(--body); text-anchor: start; }}
.mm-north path {{ fill: var(--ink); }}
.mm-north text {{ text-anchor: middle; }}
.minimap {{ padding: 0 16px 16px; display: grid; gap: 8px; }}
.minimap svg {{ display: block; width: 100%; max-width: 440px; height: auto; border: 1px solid var(--rule); }}
.mm-cap {{ margin: 0; font-size: 13px; color: var(--muted); max-width: 62ch; }}
.mm-cap strong {{ color: var(--ink); }}
.mm-cap a {{ font-weight: 600; overflow-wrap: anywhere; }}

/* Neighbor flags */
.tally.hot b {{ color: var(--attention); }}
.flagcell {{ min-width: 180px; }}
.flag {{ display: inline-block; margin: 2px 4px 2px 0; padding: 1px 8px; border-radius: 3px; font-size: 12px; font-weight: 600; white-space: nowrap; border: 1px solid transparent; }}
.flag.fs-open {{ background: var(--attention); color: var(--sheet); }}
.flag.fs-upcoming {{ background: var(--attention-bg); color: var(--attention); border-color: var(--attention); }}
.flag.fs-info {{ background: var(--early-bg); color: var(--early); }}
.flag.fs-past {{ color: var(--muted); border-color: var(--rule); font-weight: 500; }}
.noflag {{ color: var(--muted); font-size: 12.5px; }}
.nbr {{ display: grid; grid-template-columns: minmax(200px, .55fr) minmax(0, 1.6fr); border-bottom: 1px solid var(--rule-strong); background: var(--paper); }}
.nbr-head {{ padding: 14px 18px; border-right: 1px solid var(--rule); }}
.nbr-head p {{ margin: 4px 0 0; font-size: 12.5px; color: var(--muted); }}
.nbr-list {{ list-style: none; margin: 0; padding: 0; display: grid; }}
.nbr-list li {{ display: grid; grid-template-columns: 104px minmax(0, 1fr); gap: 12px; padding: 12px 18px; border-bottom: 1px solid var(--rule); }}
.nbr-list li:last-child {{ border-bottom: 0; }}
.nbr-list strong {{ font-size: 14.5px; }}
.nbr-list p {{ margin: 2px 0 4px; font-size: 13.5px; max-width: 72ch; }}
.nbr-list small {{ font-size: 12px; color: var(--muted); }}
.nbr-list small a {{ font-family: var(--mono); }}
.fstat {{ align-self: start; justify-self: start; padding: 2px 8px; border-radius: 3px; font: 700 10.5px/1.4 var(--body); letter-spacing: .07em; text-transform: uppercase; }}
li.fs-open .fstat {{ background: var(--attention); color: var(--sheet); }}
li.fs-upcoming .fstat {{ background: var(--attention-bg); color: var(--attention); }}
li.fs-info .fstat {{ background: var(--early-bg); color: var(--early); }}
li.fs-past .fstat {{ color: var(--muted); border: 1px solid var(--rule); }}
li.fs-past strong, li.fs-past p {{ color: var(--muted); }}
.nbr-how {{ grid-column: 1 / -1; margin: 0; padding: 12px 18px; border-top: 1px solid var(--rule); font-size: 13.5px; background: var(--sheet); }}
.nbr-how .sel {{ font-family: var(--mono); font-size: 12.5px; user-select: all; }}
.nbr-how .muted {{ color: var(--muted); font-size: 12px; }}

/* Approval timeline */
.tl-band {{ display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(300px, 1fr); align-items: center; border-bottom: 1px solid var(--rule-strong); }}
.tl {{ list-style: none; margin: 0; padding: 14px 16px 12px; display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); }}
.tl li {{ position: relative; display: grid; justify-items: center; gap: 2px; text-align: center; min-width: 0; }}
.tl li::before {{ content: ""; position: absolute; top: 10px; left: 0; right: 0; height: 2px; background: var(--rule-strong); }}
.tl li:first-child::before {{ left: 50%; }}
.tl li:last-child::before {{ right: 50%; }}
.tl li.done::before {{ background: var(--t); }}
.tl li.now::before {{ background: linear-gradient(90deg, var(--t) 50%, var(--rule-strong) 50%); }}
.tl li.now:first-child::before {{ background: var(--rule-strong); }}
.tl li.now:last-child::before {{ background: var(--t); }}
.tl .pt {{ position: relative; z-index: 1; width: 14px; height: 14px; margin: 4px 0; border-radius: 50%; background: var(--sheet); border: 2px solid var(--rule-strong); }}
.tl .done .pt {{ background: var(--t); border-color: var(--t); }}
.tl .now .pt {{ width: 22px; height: 22px; margin: 0; background: var(--t); border: 3px solid var(--sheet); box-shadow: 0 0 0 2px var(--t), 0 0 0 7px var(--tb); }}
.tl b {{ font: 600 10.5px/1.2 var(--body); letter-spacing: .07em; text-transform: uppercase; color: var(--muted); margin-top: 4px; }}
.tl .now b {{ color: var(--t); font-weight: 700; }}
.tl small {{ font-size: 11.5px; color: var(--muted); font-variant-numeric: tabular-nums; min-height: 1.3em; }}
.tl .now small {{ color: var(--ink); font-weight: 500; }}
.tl-note {{ margin: 0; padding: 12px 18px; border-left: 1px solid var(--rule-strong); font-size: 14px; align-self: stretch; display: grid; align-content: center; }}
.stagecell {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; }}
.mini {{ display: inline-flex; align-items: center; }}
.mini i {{ width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--rule-strong); background: var(--sheet); display: block; }}
.mini i + i {{ margin-left: 10px; position: relative; }}
.mini i + i::before {{ content: ""; position: absolute; right: 100%; top: 2.5px; width: 10px; height: 1.5px; background: var(--rule-strong); margin-right: 1.5px; }}
.mini i.done, .mini i.now {{ background: var(--t); border-color: var(--t); }}
.mini i.done + i::before, .mini i.now + i.done::before {{ background: var(--t); }}
.mini i.done + i.now::before {{ background: var(--t); }}
.mini i.now {{ width: 13px; height: 13px; box-shadow: 0 0 0 3px var(--tb); }}
.mini i.now + i::before {{ top: 4.5px; }}

.colophon {{ font-size: 13px; color: var(--muted); border-top: 1px solid var(--rule-strong); padding-top: 16px; display: grid; gap: 8px; max-width: 80ch; }}
.colophon ul {{ margin: 0; padding-left: 18px; display: grid; gap: 4px; }}
.sources a {{ font-weight: 600; }}
.applink {{ font: 500 13px var(--mono); white-space: nowrap; }}
.applink::after {{ content: " ↗"; font-family: var(--body); }}
.apps code a {{ color: var(--accent); }}
.drawing figcaption {{ display: grid; gap: 6px; }}
.drawing .cap {{ color: var(--muted); }}
.drawing .src {{ display: grid; gap: 1px; padding: 8px 10px; background: var(--accent-soft); border-radius: 2px; font-size: 13px; }}
.drawing .src a {{ font-weight: 600; text-decoration: none; overflow-wrap: anywhere; }}
.drawing .src a:hover {{ text-decoration: underline; }}
.drawing .src small {{ color: var(--muted); font-size: 12px; }}

dialog {{ border: 0; padding: 0; background: transparent; max-width: 96vw; max-height: 94vh; }}
dialog::backdrop {{ background: rgba(10, 16, 15, .82); }}
dialog img {{ display: block; max-width: 96vw; max-height: 86vh; background: #fff; }}
dialog .bar {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; color: #fff; font-size: 13px; padding: 8px 2px 0; }}
dialog button {{ font: 600 13px var(--body); background: #fff; color: #18211f; border: 0; border-radius: 4px; padding: 6px 12px; cursor: pointer; }}

@media (max-width: 900px) {{
  .sheet-body {{ grid-template-columns: minmax(0, 1fr); }}
  .leftcol {{ border-right: 0; border-bottom: 1px solid var(--rule-strong); }}
  .tl-band {{ grid-template-columns: minmax(0, 1fr); }}
  .tl-note {{ border-left: 0; border-top: 1px solid var(--rule); }}
  .mast {{ grid-template-columns: minmax(0, 1fr); }}
  .overview-map {{ grid-template-columns: minmax(0, 1fr); }}
  .nbr {{ grid-template-columns: minmax(0, 1fr); }}
  .nbr-head {{ border-right: 0; border-bottom: 1px solid var(--rule); }}
}}
@media (max-width: 560px) {{
  .sheet-head {{ grid-template-columns: auto minmax(0, 1fr); padding: 14px; }}
  .stage {{ grid-column: 1 / -1; max-width: none; }}
  .grid {{ grid-template-columns: minmax(0, 1fr); }}
  .cell:nth-child(odd) {{ border-right: 0; }}
  .tallies {{ grid-template-columns: repeat(2, 1fr); }}
  .tally:first-child {{ grid-column: 1 / -1; }}
  .tally:nth-child(even) {{ border-left: 0; }}
  .tally:nth-child(n+2) {{ border-top: 1px solid var(--rule); }}
  .tally:nth-child(n+3) {{ border-top: 1px solid var(--rule); }}
  .nbr-list li {{ grid-template-columns: minmax(0, 1fr); gap: 6px; }}
  .foot {{ grid-template-columns: 1fr 1fr; }}
  .foot > div:nth-child(2) {{ border-right: 0; }}
  .foot > div:nth-child(3) {{ grid-column: 1 / -1; border-top: 1px solid var(--rule); }}
  .apps li {{ grid-template-columns: minmax(0, 1fr) auto; }}
  .apps li span {{ grid-column: 1 / -1; grid-row: 2; color: var(--muted); }}
  .thumb, .thumb img {{ width: 88px; }}
  .tl {{ padding: 12px 6px 10px; }}
  .tl b {{ font-size: 9.5px; letter-spacing: .03em; }}
  .tl small {{ font-size: 10.5px; }}
}}
@media (prefers-reduced-motion: no-preference) {{ .index td a, .foot .case {{ transition: color .15s; }} }}
</style>

<div class="wrap">
  <header class="mast">
    <div>
      <p class="homelink"><a href="https://sbvna.com" target="_blank" rel="noopener">← Back to sbvna.com</a></p>
      <p class="eyebrow">Southeast Boise · Neighborhood planning watch</p>
      <h1>{hood}<br>Development</h1>
      <p class="notice" role="note"><strong>Screening tool.</strong> This page is compiled automatically from public City of Boise data sources and can be incomplete, out of date, or misread from the filed documents. It is not an official city record and is not affiliated with the City of Boise. Check the linked case files before relying on anything here.</p>
      <p class="lede">Active zoning and planning cases in the South Boise Village neighborhood association area, with the drawings filed for each. Updated {updated}.</p>
    </div>
    <div class="tallies" role="list">
      <div class="tally" role="listitem"><b>{n}</b><span>Active projects</span></div>
      <div class="tally" role="listitem"><b>{new_n}</b><span>New this week</span></div>
      <div class="tally hot" role="listitem"><b>{open_n}</b><span>Open for input</span></div>
      <div class="tally" role="listitem"><b>{review}</b><span>In review</span></div>
      <div class="tally" role="listitem"><b>{decision}</b><span>At decision</span></div>
    </div>
  </header>

  <section class="index" aria-label="Project index">
    <table>
      <thead><tr><th>Address</th><th>Type</th><th>Neighbor input</th><th>Application</th><th>Stage</th><th>Last activity</th></tr></thead>
      <tbody>{index_rows}</tbody>
    </table>
  </section>

  {recent}

  {overview}

  <div class="sheets">{sheets}</div>

  <footer class="colophon">
    <div><span class="lbl">Not shown</span><ul>{inactive}</ul></div>
    <div class="sources"><span class="lbl">Public data sources</span><ul>
      <li><a href="https://www.cityofboise.org/departments/planning-and-development-services/planning/zoning/maps/development-tracker/" target="_blank" rel="noopener">City of Boise Development Tracker</a>: list of active cases and their neighborhood association</li>
      <li><a href="https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Development_Tracker_Open_Data/FeatureServer" target="_blank" rel="noopener">Development Tracker open data (ArcGIS feature service)</a>: the data feed this page reads</li>
      <li><a href="https://permits.cityofboise.org/CitizenAccess/Default.aspx" target="_blank" rel="noopener">City of Boise Permitting &amp; Licensing</a>: case records, related records and filed documents (drawings, letters, staff decisions)</li>
      <li><a href="https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Ada_County_Parcels/FeatureServer" target="_blank" rel="noopener">Ada County parcels (City of Boise ArcGIS)</a>: lot lines on the maps and parcels within notice distances</li>
      <li><a href="https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/BoiseNeighborhoodAssociations/FeatureServer" target="_blank" rel="noopener">Boise neighborhood association boundaries (City of Boise ArcGIS)</a>: the South Boise Village boundary</li>
      <li><a href="https://codelibrary.amlegal.com/codes/boise_id/latest/overview" target="_blank" rel="noopener">Boise City Code, Title 11 (zoning)</a>: standards cited in the attributes, such as ADU size and height limits</li>
    </ul></div>
    <p>Cases come from the City of Boise Development Tracker, filtered to the South Boise Village neighborhood association. Attributes and drawings come from the public documents on each case in the city's Permitting &amp; Licensing system. Figures are as filed by applicants and can change during review; check the case file before relying on them.</p>
  </footer>
</div>

<dialog id="lightbox" aria-label="Drawing">
  <img id="lb-img" alt="">
  <div class="bar"><span id="lb-cap"></span><button type="button" id="lb-close">Close</button></div>
</dialog>

<script>
const IMGS = {img_json};
document.querySelectorAll('.left[data-deadline]').forEach(el => {{
  const d = new Date(el.dataset.deadline + 'T23:59:59'), now = new Date();
  const left = Math.ceil((d - now) / 86400000) - 1;
  el.textContent = left > 0 ? ` · ${{left}} day${{left === 1 ? '' : 's'}} left` : left === 0 ? ' · last day' : ' · passed';
}});
document.querySelectorAll('img[data-ref]').forEach(im => {{ const r = IMGS[im.dataset.ref]; if (r) im.src = r.src; }});
document.querySelectorAll('.drawing').forEach(fig => {{
  const main = fig.querySelector('img.main'), cap = fig.querySelector('figcaption');
  fig.querySelectorAll('.thumb').forEach(t => t.addEventListener('click', () => {{
    const r = IMGS[t.dataset.src]; if (!r) return;
    main.src = r.src; main.dataset.ref = t.dataset.src; main.alt = r.cap; cap.innerHTML = r.caphtml;
    fig.querySelectorAll('.thumb').forEach(x => x.classList.toggle('on', x === t));
  }}));
}});
const lb = document.getElementById('lightbox');
document.querySelectorAll('.zoom').forEach(z => z.addEventListener('click', () => {{
  const im = z.querySelector('img'), r = IMGS[im.dataset.ref]; if (!r) return;
  document.getElementById('lb-img').src = r.src; document.getElementById('lb-img').alt = r.cap;
  document.getElementById('lb-cap').textContent = r.cap;
  if (lb.showModal) lb.showModal();
}}));
document.getElementById('lb-close').addEventListener('click', () => lb.close());
lb.addEventListener('click', e => {{ if (e.target === lb) lb.close(); }});
</script>
'''

if __name__ == "__main__":
    data = json.load(open(sys.argv[1]))
    mp = os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), "map.json")
    out = build(data, sys.argv[2], json.load(open(mp)) if os.path.exists(mp) else None)
    open(sys.argv[3], "w").write(out)
    print(f"wrote {sys.argv[3]} ({len(out)//1024} KB)")
