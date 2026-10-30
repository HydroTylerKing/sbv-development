"""Lot map data for the South Boise Village report.

  python3 sbvmap.py notice RADIUS_MAP.pdf "SUBJECT ADDRESS"
      Reads a City of Boise "NOTICING RADIUS MAP" PDF and prints the addresses of the parcels the city selected
      for mailed notice (the dots drawn in the legend's "Selected addresses" color), matched to county parcels.
      Copy the printed list into the project's "notice" -> "addresses" in data/projects.json.

  python3 sbvmap.py build data/projects.json data/map.json
      Fetches the neighborhood boundary and county parcels from the City of Boise ArcGIS services and writes
      projected, simplified SVG geometry: parcels, street labels, each project's lot and its notice area.
      Each project needs "lot_addresses" (site addresses as the county lists them, e.g. "1911 S MANITOU AVE").
"""
import json, math, sys
import requests
from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.ops import unary_union

ARC = "https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services"
PARCELS = f"{ARC}/Ada_County_Parcels/FeatureServer/142/query"
HOODS = f"{ARC}/BoiseNeighborhoodAssociations/FeatureServer/0/query"
HOOD = "South Boise Village"


def addr(f):
    return " ".join((f["properties"].get("ADDRESS") or "").split())


def fetch_boundary():
    r = requests.get(HOODS, params={"where": f"ASSOCIATIONNAME='{HOOD}'", "outFields": "ASSOCIATIONNAME",
                                    "outSR": 4326, "f": "geojson"}, timeout=60)
    return shape(r.json()["features"][0]["geometry"])


def fetch_parcels(bounds, pad=0.0015):
    x0, y0, x1, y1 = bounds
    env = f"{x0 - pad},{y0 - pad},{x1 + pad},{y1 + pad}"
    feats, off = [], 0
    while True:
        r = requests.get(PARCELS, params={"where": "1=1", "geometry": env, "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                                          "spatialRel": "esriSpatialRelIntersects", "outFields": "PARCEL,ADDRESS",
                                          "outSR": 4326, "f": "geojson", "resultOffset": off, "resultRecordCount": 2000}, timeout=120)
        fs = r.json().get("features", [])
        feats += [f for f in fs if f.get("geometry")]
        if len(fs) < 2000:
            return feats
        off += 2000


# ---------- notice parcels from the city's radius map ----------
def notice(pdf_path, subject_address):
    import pdfplumber
    pg = pdfplumber.open(pdf_path).pages[0]
    legend_x = pg.width * 0.77
    words = pg.extract_words()
    label = next((w for w in words if w["text"].lower().startswith("selected") and w["x0"] > legend_x
                  and any(v["text"].lower().startswith("address") and abs(v["top"] - w["top"]) < 3 for v in words)), None)
    if not label:
        raise SystemExit("legend entry 'Selected addresses' not found: this map's text is not machine-readable. Render the PDF, "
                         "read the shaded parcels' addresses yourself, and enter them in the project's notice.addresses.")
    small = [o for o in pg.curves if o.get("non_stroking_color") and (o["x1"] - o["x0"]) < 6]
    sym = min((o for o in small if o["x0"] > legend_x),
              key=lambda o: abs((o["top"] + o["bottom"]) / 2 - (label["top"] + label["bottom"]) / 2) + abs(o["x1"] - label["x0"]))
    color = sym["non_stroking_color"]
    same = lambda c: c and len(c) == len(color) and all(abs(a - b) < 0.01 for a, b in zip(c, color))
    dots = [o for o in small if o["x1"] < legend_x and same(o["non_stroking_color"])]
    nums = [w for w in words if w["text"].isdigit() and w["x1"] < legend_x]
    picked = []
    for d in dots:
        cx, cy = (d["x0"] + d["x1"]) / 2, (d["top"] + d["bottom"]) / 2
        picked.append(min(nums, key=lambda w: math.hypot(w["x0"] - cx, (w["top"] + w["bottom"]) / 2 - cy))["text"])
    boundary = fetch_boundary()
    parcels = fetch_parcels(boundary.bounds)
    subj = [f for f in parcels if addr(f) == subject_address.upper()]
    if not subj:
        raise SystemExit(f"subject parcel {subject_address} not found")
    sg = unary_union([shape(f["geometry"]) for f in subj])
    near = [f for f in parcels if shape(f["geometry"]).distance(sg) < 0.0012]
    out = []
    for n in picked:
        c = sorted([f for f in near if addr(f).split(" ")[0] == n], key=lambda f: shape(f["geometry"]).distance(sg))
        if c and addr(c[0]) != subject_address.upper() and addr(c[0]) not in out:
            out.append(addr(c[0]))
        elif not c:
            print(f"warning: no parcel numbered {n} near the subject", file=sys.stderr)
    print(json.dumps(out))


# ---------- map geometry ----------
class Proj:
    def __init__(self, bounds):
        x0, y0, x1, y1 = bounds
        self.lon0, self.lat0 = x0, y1
        self.kx = math.cos(math.radians((y0 + y1) / 2)) * 111320
        self.ky = 110540

    def xy(self, lon, lat):
        return ((lon - self.lon0) * self.kx, (self.lat0 - lat) * self.ky)

    def geom(self, g):
        from shapely.ops import transform
        return transform(lambda x, y, z=None: self.xy(x, y), g)


def path(g, tol=0.4):
    g = g.simplify(tol, preserve_topology=True)
    polys = [g] if isinstance(g, Polygon) else list(getattr(g, "geoms", []))
    parts = []
    for p in polys:
        if not isinstance(p, Polygon) or p.is_empty:
            continue
        for ring in [p.exterior] + list(p.interiors):
            pts = list(ring.coords)[:-1]
            if len(pts) >= 3:
                parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
    return "".join(parts)


def street_labels(parcels, proj, boundary_m):
    import numpy as np
    groups = {}
    for f in parcels:
        a = addr(f)
        if not a or not a.split(" ")[0].isdigit():
            continue
        name = " ".join(a.split(" ")[1:])
        c = proj.geom(shape(f["geometry"])).centroid
        if boundary_m.buffer(30).contains(c):
            groups.setdefault(name, []).append((c.x, c.y))
    labels = []
    for name, pts in groups.items():
        if len(pts) < 8:
            continue
        P = np.array(pts)
        m = P.mean(axis=0)
        u, s, vt = np.linalg.svd(P - m)
        d = vt[0]
        spread = s[0] / max(s[1], 1e-6)
        if spread < 2.5:  # not a line of lots along one street
            continue
        ang = math.degrees(math.atan2(d[1], d[0]))
        if ang > 90: ang -= 180
        if ang < -90: ang += 180
        proj_t = (P - m) @ d
        # place the label in the street's longest stretch, at the median position
        t = float(np.median(proj_t))
        x, y = m + d * t
        pretty = " ".join(w.capitalize() if w not in ("W", "E", "N", "S") else w for w in name.split())
        labels.append({"name": pretty, "x": round(float(x), 1), "y": round(float(y), 1), "angle": round(ang, 1), "n": len(pts)})
    return labels


def build(projects_path, out_path):
    data = json.load(open(projects_path))
    boundary = fetch_boundary()
    parcels = fetch_parcels(boundary.bounds)
    proj = Proj(boundary.buffer(0.0012).bounds)
    bm = proj.geom(boundary)
    clip = bm.buffer(140)
    by_addr = {}
    for f in parcels:
        by_addr.setdefault(addr(f), []).append(f)
    parcel_paths = []
    for f in parcels:
        g = proj.geom(shape(f["geometry"]))
        if g.intersects(clip):
            parcel_paths.append(path(g.intersection(clip)))
    out = {"source": "City of Boise ArcGIS: Ada_County_Parcels, BoiseNeighborhoodAssociations",
           "boundary": path(bm, 1.5), "parcels": "".join(parcel_paths),
           "streets": street_labels(parcels, proj, bm), "projects": {}}
    minx, miny, maxx, maxy = clip.bounds
    out["viewBox"] = [round(minx), round(miny), round(maxx - minx), round(maxy - miny)]
    for p in data["projects"]:
        lots = [f for a in p.get("lot_addresses", []) for f in by_addr.get(a.upper(), [])]
        if not lots:
            print(f"warning: no lot found for {p['id']} {p.get('lot_addresses')}", file=sys.stderr)
            continue
        lot = proj.geom(unary_union([shape(f["geometry"]) for f in lots]))
        rec = {"lot": path(lot), "cx": round(lot.centroid.x, 1), "cy": round(lot.centroid.y, 1),
               "bbox": [round(v, 1) for v in lot.bounds]}
        nt = p.get("notice") or {}
        if nt.get("radius_ft"):
            # notice mailed to every parcel within the stated distance of the project's property lines
            ring = lot.buffer(nt["radius_ft"] * 0.3048)
            nt["addresses"] = sorted({addr(f) for f in parcels if addr(f) and proj.geom(shape(f["geometry"])).intersects(ring)
                                      and addr(f) not in [a.upper() for a in p.get("lot_addresses", [])]})
            rec["radius_m"] = round(nt["radius_ft"] * 0.3048, 1)
        if nt.get("addresses"):
            ns = [f for a in nt["addresses"] for f in by_addr.get(a.upper(), [])]
            missing = [a for a in nt["addresses"] if not by_addr.get(a.upper())]
            if missing:
                print(f"warning: notice parcels not found for {p['id']}: {missing}", file=sys.stderr)
            if ns:
                area = proj.geom(unary_union([shape(f["geometry"]) for f in ns]))
                whole = unary_union([area, lot])
                rec["notice"] = path(area)
                # each notified property with its own lot lines, for drawing property lines
                rec["notice_parcels"] = [{"address": addr(f), "d": path(proj.geom(shape(f["geometry"])), 0.2)} for f in ns]
                rec["notice_outline"] = path(whole.buffer(1.5).buffer(-1.5))
                rec["notice_bbox"] = [round(v, 1) for v in whole.bounds]
                rec["notice_count"] = len(ns)
        # nearby parcels for the project's own close-up map
        zoom = (rec.get("notice_bbox") or rec["bbox"])
        zx0, zy0, zx1, zy1 = zoom
        cx, cy = (zx0 + zx1) / 2, (zy0 + zy1) / 2
        half = max(zx1 - zx0, zy1 - zy0) / 2 + 45
        win = Polygon([(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)])
        near = []
        for f in parcels:
            g = proj.geom(shape(f["geometry"]))
            if g.intersects(win):
                near.append(path(g.intersection(win), 0.2))
        rec["zoom"] = {"viewBox": [round(cx - half, 1), round(cy - half, 1), round(2 * half, 1), round(2 * half, 1)],
                       "parcels": "".join(near)}
        out["projects"][p["id"]] = rec
    json.dump(out, open(out_path, "w"))
    print(f"wrote {out_path}: {len(parcel_paths)} parcels, {len(out['streets'])} street labels, {len(out['projects'])} projects")


if __name__ == "__main__":
    if sys.argv[1] == "notice":
        notice(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "build":
        build(sys.argv[2], sys.argv[3])
