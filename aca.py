"""Fetch Boise Accela Citizen Access (CitizenAccess) record details and documents.

Usage:
  python3 aca.py RECORD_ID OUTDIR [--all | --match REGEX]
Writes OUTDIR/record.json (details + document list) and downloads matching documents.
Default match: elevation / architectural / building drawings / plans.
"""
import json, os, re, sys, html, time
import requests
from bs4 import BeautifulSoup

BASE = "https://permits.cityofboise.org/CitizenAccess"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
DEFAULT_MATCH = r"ELEV|ARCHITECT|BUILDING PLAN|PLAN SET|DRAWINGS|RENDER|FLOOR PLAN|SITE PLAN|LETTER OF (INTENT|EXPLANATION)|PROJECT (DESCRIPTION|NARRATIVE)|DETAIL"


def text_of(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def hidden_fields(soup):
    return {i.get("name"): i.get("value", "") for i in soup.select("input[type=hidden]") if i.get("name")}


def get(s, url, **kw):
    """GET with retries: the city site answers 503 under bursts of requests."""
    for wait in (0, 5, 15, 40, 90):
        time.sleep(wait)
        r = s.get(url, timeout=kw.pop("timeout", 60), **kw)
        if r.status_code not in (429, 500, 502, 503, 504):
            return r
    r.raise_for_status()
    return r


def open_record(s, rid):
    r = get(s, f"{BASE}/Cap/GlobalSearchResults.aspx", params={"QueryText": rid})
    r.raise_for_status()
    if "CapDetail.aspx" not in r.url:
        # search results page: follow the first CapDetail link for this record
        soup = BeautifulSoup(r.text, "html.parser")
        a = next((a for a in soup.select("a[href*=CapDetail]") if rid in text_of(a)), None) or soup.select_one("a[href*=CapDetail]")
        if not a:
            raise RuntimeError(f"{rid}: record page not found")
        r = s.get(requests.compat.urljoin(r.url, html.unescape(a["href"])), timeout=60)
    return r


def parse_details(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    t = text_of(soup)
    out = {}
    m = re.search(r"Record Status:\s*(.+?)\s+(?:Add to Existing Project|Create a New)", t)
    if m: out["status"] = m.group(1).strip()
    m = re.search(r"Project Location\s+(.+?)\s+\*", t)
    if m: out["location"] = m.group(1).strip()
    m = re.search(r"Project Description:\s*(.+?)\s+More Details", t)
    if m: out["project_description"] = m.group(1).strip()
    m = re.search(r"Applicant:\s*(.+?)\s+(?:Main Phone|Project Description|Owner|Licensed)", t)
    if m: out["applicant"] = m.group(1).strip()
    m = re.search(r"More Details(.+?)(?:Print/View Summary|Fees All fees)", t)
    if m: out["more_details_text"] = m.group(1).replace("&nbsp;", " ").strip()
    return out


def list_documents(s, detail_url, page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    fr = soup.select_one("iframe[id$=iframeAttachmentList]")
    if not fr:
        return None, []
    url = requests.compat.urljoin(detail_url, html.unescape(fr["src"]))
    r = s.get(url, headers={"Referer": detail_url}, timeout=60)
    soup = BeautifulSoup(r.text, "html.parser")
    docs = []
    for row in soup.select("table[id*=gdvAttachmentList] tr"):
        link = row.select_one("a[id*=lnkFileName]")
        if not link:
            continue
        cells = [text_of(td) for td in row.select("td")]
        target = re.search(r"__doPostBack\('([^']+)'", html.unescape(link.get("href", "")))
        docs.append({"name": text_of(link), "cells": cells, "event_target": target.group(1) if target else None})
    return (url, r.text), docs


def download(s, list_url, list_html, doc, dest):
    soup = BeautifulSoup(list_html, "html.parser")
    form = hidden_fields(soup)
    form["__EVENTTARGET"] = doc["event_target"]
    form["__EVENTARGUMENT"] = ""
    action = soup.select_one("form")["action"]
    post_url = requests.compat.urljoin(list_url, html.unescape(action))
    r = s.post(post_url, data=form, headers={"Referer": list_url}, timeout=180, allow_redirects=True)
    ctype = r.headers.get("content-type", "")
    if "html" in ctype:
        # Accela often answers with a script that opens the file handler URL
        m = re.search(r"(?:window\.open|location\.href\s*=|src=)\s*\(?['\"]([^'\"]*(?:FileDownload|Download|fileupload)[^'\"]*)['\"]", r.text, re.I)
        if not m:
            raise RuntimeError(f"download link not found for {doc['name']}")
        r = s.get(requests.compat.urljoin(post_url, html.unescape(m.group(1))), headers={"Referer": list_url}, timeout=300)
    cd = r.headers.get("content-disposition", "")
    fn = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
    name = fn.group(1) if fn else re.sub(r"[^\w.-]+", "_", doc["name"]) + ".pdf"
    path = os.path.join(dest, re.sub(r"[^\w.() -]+", "_", requests.utils.unquote(name)))
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path = f"{base} ({n}){ext}"
        n += 1
    with open(path, "wb") as f:
        f.write(r.content)
    return path, len(r.content), r.headers.get("content-type", "")


def main():
    rid, out = sys.argv[1], sys.argv[2]
    pattern = None if "--all" in sys.argv else (sys.argv[sys.argv.index("--match") + 1] if "--match" in sys.argv else DEFAULT_MATCH)
    os.makedirs(out, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = UA
    r = open_record(s, rid)
    rec = {"record_id": rid, "detail_url": r.url, **parse_details(r.text)}
    lst, docs = list_documents(s, r.url, r.text)
    rec["documents"] = []
    first = True
    for d in docs:
        entry = {"name": d["name"], "cells": d["cells"]}
        if lst and d["event_target"] and (pattern is None or re.search(pattern, " ".join(d["cells"]), re.I)):
            for attempt in range(2):
                try:
                    if not first:
                        time.sleep(2)
                        # The list page goes stale after a download: reopen the record in a fresh session.
                        s = requests.Session()
                        s.headers["User-Agent"] = UA
                        r2 = open_record(s, rid)
                        lst, _ = list_documents(s, r2.url, r2.text)
                    first = False
                    path, size, ctype = download(s, lst[0], lst[1], d, out)
                    entry.update(file=path, bytes=size, content_type=ctype)
                    entry.pop("error", None)
                    break
                except Exception as e:
                    entry["error"] = str(e)
                    first = False
        rec["documents"].append(entry)
    json.dump(rec, open(os.path.join(out, "record.json"), "w"), indent=2)
    print(json.dumps({k: v for k, v in rec.items() if k != "more_details_text"}, indent=1))


if __name__ == "__main__":
    main()
