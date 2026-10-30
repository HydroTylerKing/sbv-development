"""Find every Planning/Building record tied to a project: the case's related-records tree plus an address search.

Usage: python3 related.py RECORD_ID "ADDRESS" OUT.json
Prints one line per record (newest first). Only Planning and Building modules are kept, so unrelated
records at the same address (business or worker licenses, police, etc.) never enter the report.
"""
import json, os, re, sys
import requests
from bs4 import BeautifulSoup
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # aca.py sits beside this file; needed under python -I
from aca import BASE, UA, get, open_record, text_of

KEEP_MODULES = {"Planning", "Building"}


def tree(s, rid):
    r = open_record(s, rid)
    url = r.url.split("?")[0] + "/GetBuildCapTree"
    out = []
    for show_all in ("false", "true"):
        x = s.post(url, json={"moduleName": "Planning", "isShowAll": show_all},
                   headers={"Content-Type": "application/json; charset=utf-8", "Referer": r.url,
                            "X-Requested-With": "XMLHttpRequest"}, timeout=60)
        if x.status_code != 200:
            continue
        d = x.json().get("d") or ""
        soup = BeautifulSoup(d, "html.parser")
        for tr in soup.select("tr"):
            c = [text_of(td) for td in tr.select("td")]
            ids = [v for v in c if re.fullmatch(r"[A-Z]{3}\d{2}-\d{5}", v)]
            if ids:
                rec_type = next((v for v in c if v and v not in ids and not re.fullmatch(r"[\d/]+|View", v)), "")
                date = next((v for v in c if re.fullmatch(r"\d{2}/\d{2}/\d{4}", v)), "")
                out.append({"record_id": ids[0], "type": rec_type, "date": date, "source": "related tree"})
    return out


def parse_address_results(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    rows = []
    for tb in soup.select("table"):
        head = [text_of(th) for th in tb.select("tr th")] or []
        for tr in tb.select("tr"):
            c = [text_of(td) for td in tr.select("td")]
            if len(c) >= 8 and re.fullmatch(r"\d{2}/\d{2}/\d{4}", c[0] or "") and re.match(r"[A-Z0-9]{3,}", c[1] or ""):
                rows.append({"date": c[0], "record_id": c[1], "type": c[2], "module": c[3], "project": c[5],
                             "address": c[6], "status": c[7], "source": "address search"})
        if rows:
            break
    return rows


def address_search(s, address):
    q = re.sub(r",.*$", "", address).replace("–", "-").split("-")[0].strip()  # "1607–1613 S X AVE" -> "1607"
    if not re.search(r"[A-Za-z]", q):
        q = address.replace("–", " ")
    q = re.sub(r"\b(?:W|E|N|S)\b\.?", lambda m: m.group(0).upper(), q)
    r = get(s, f"{BASE}/Cap/GlobalSearchResults.aspx", params={"QueryText": q})
    if "CapDetail.aspx" in r.url:  # a single hit jumps straight to the record
        return []
    # The city's search is fuzzy: keep only rows whose address has the same house number and street name.
    m = re.match(r"\s*(\d+)\D+?\s([A-Za-z0-9]+)\s+(?:AVE|ST|DR|RD|LN|WAY|BLVD|CT|PL|LOOP|ALY)\b", address.upper().replace("–", "-"))
    num, street = (m.group(1), m.group(2)) if m else (None, None)

    def same_place(a):
        a = a.upper()
        return num is None or (re.search(rf"(?<!\d){num}\b", a) and re.search(rf"\b{street}\b", a))

    rows = parse_address_results(r.text)
    return [x for x in rows if x["module"] in KEEP_MODULES and same_place(x.get("address", ""))
            and not re.match(r"(ELE|MEC|PLM|PLU|SGN|FIR)\d", x["record_id"])]  # routine trade permits carry no plans


def main():
    rid, address, out = sys.argv[1], sys.argv[2], sys.argv[3]
    since = sys.argv[sys.argv.index("--since") + 1] if "--since" in sys.argv else "0000-00-00"  # YYYY-MM-DD
    s = requests.Session()
    s.headers["User-Agent"] = UA
    seen = {}
    for rec in tree(s, rid) + address_search(s, address):
        seen.setdefault(rec["record_id"], {}).update({k: v for k, v in rec.items() if v})
    iso = lambda d: f"{d[6:]}-{d[:2]}-{d[3:5]}" if d else ""
    seen = {k: v for k, v in seen.items() if v.get("source") == "related tree" or iso(v.get("date", "")) >= since}
    res = sorted(seen.values(), key=lambda x: x.get("date", "")[6:] + x.get("date", "")[:5], reverse=True)
    json.dump(res, open(out, "w"), indent=2)
    for x in res:
        print(x["record_id"], "|", x.get("type"), "|", x.get("module", ""), "|", x.get("status", ""), "|", x.get("date"), "|", x.get("address", ""))


if __name__ == "__main__":
    main()
