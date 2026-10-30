"""Render one PDF page to a report image, black out private details, and stamp the City of Boise source on it.

Usage:
  python3 redact.py IN.pdf PAGE OUT.jpg --record CZC26-00249 --retrieved 2026-10-23
        [--terms "Krista Laurino" "1303 W Howard"] [--box x0,y0,x1,y1 ...] [--dpi 200] [--preview PREVIEW.png]

What gets blacked out:
  * every phone number and email address found on the page (OCR, so it also works on flattened scans),
    unless --keep-contacts is given
  * optionally, any word sequence given with --terms and any --box region (fractions of the page, 0-1)
Prints a JSON report of what was redacted.
"""
import argparse, json, os, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

PHONE = re.compile(r"^\(?\d{3}\)?[-.\s]?\d{3}[-.]\d{4}\b|^\d{3}[-.]\d{4}$|^\d{3}\.\d{3}\.\d{4}$")
EMAIL = re.compile(r"\S+@\S+\.\S+")
MAX_W = 1800


def render(pdf, page, dpi, outdir):
    base = os.path.join(outdir, "pg")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-singlefile", "-f", str(page), "-l", str(page), pdf, base],
                   check=True, capture_output=True)
    return Image.open(base + ".png").convert("RGB")


def ocr_words(img, outdir):
    """Word boxes from tesseract, at two orientations' worth of page segmentation (sparse text suits drawings)."""
    path = os.path.join(outdir, "ocr.png")
    img.save(path)
    words = []
    for psm in ("11", "3"):
        r = subprocess.run(["tesseract", path, "stdout", "--psm", psm, "tsv"], capture_output=True, text=True)
        for line in r.stdout.splitlines()[1:]:
            c = line.split("\t")
            if len(c) == 12 and c[11].strip():
                x, y, w, h = map(int, c[6:10])
                words.append({"t": c[11].strip(), "box": (x, y, x + w, y + h), "line": (psm, c[2], c[3], c[4])})
    return words


def norm(t):
    return re.sub(r"[^a-z0-9@.]", "", t.lower())


def find_terms(words, terms):
    hits = []
    seq = [norm(w["t"]) for w in words]
    for term in terms:
        parts = [norm(p) for p in term.split() if norm(p)]
        n = len(parts)
        for i in range(len(words) - n + 1):
            if all(seq[i + k] == parts[k] or (len(parts[k]) > 3 and seq[i + k].startswith(parts[k])) for k in range(n)):
                # the words must sit on one OCR line to count as a match
                if len({words[i + k]["line"] for k in range(n)}) == 1:
                    hits.append((term, [words[i + k]["box"] for k in range(n)]))
    return hits


def union(boxes, pad):
    return (min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad, max(b[2] for b in boxes) + pad, max(b[3] for b in boxes) + pad)


def stamp(img, text):
    """Add a band under the drawing naming its source. Kept outside the drawing so nothing is covered."""
    w, h = img.size
    band = max(34, w // 48)
    out = Image.new("RGB", (w, h + band), (255, 255, 255))
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    d.rectangle((0, h, w, h + band), fill=(29, 92, 99))
    size = int(band * 0.46)
    font = None
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",  # macOS
              "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):  # Windows
        if os.path.exists(f):
            font = ImageFont.truetype(f, size)
            break
    if font is None:
        try:
            font = ImageFont.load_default(size=size)  # Pillow 10.1+
        except TypeError:
            font = ImageFont.load_default()
    while d.textlength(text, font=font) > w - 2 * band and size > 9 and hasattr(font, "path"):
        size -= 1
        font = ImageFont.truetype(font.path, size)
    d.text((band // 2, h + (band - size) // 2 - 1), text, fill=(255, 255, 255), font=font)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf"); ap.add_argument("page", type=int); ap.add_argument("out")
    ap.add_argument("--record", required=True); ap.add_argument("--retrieved", required=True)
    ap.add_argument("--terms", nargs="*", default=[]); ap.add_argument("--box", nargs="*", default=[])
    ap.add_argument("--dpi", type=int, default=200); ap.add_argument("--preview")
    ap.add_argument("--keep-contacts", action="store_true", help="don't black out phone numbers and emails")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        img = render(a.pdf, a.page, a.dpi, tmp)
        words = ocr_words(img, tmp)
    W, H = img.size
    pad = max(3, a.dpi // 40)
    rects, report = [], {"phones": [], "emails": [], "terms": [], "boxes": len(a.box)}
    for w in ([] if a.keep_contacts else words):
        t = w["t"]
        if EMAIL.search(t):
            rects.append(union([w["box"]], pad)); report["emails"].append(t)
        elif PHONE.search(t.replace("O", "0")):
            rects.append(union([w["box"]], pad)); report["phones"].append(t)
    # phone numbers split across words, e.g. "(208) 555-1234" or "208 555 1234"
    for i in range(0 if a.keep_contacts else len(words) - 2):
        trio = " ".join(words[i + k]["t"] for k in range(3))
        if len({words[i + k]["line"] for k in range(3)}) == 1 and re.fullmatch(r"\(?\d{3}\)?\s\d{3}[-\s]\d{4}", trio):
            rects.append(union([words[i + k]["box"] for k in range(3)], pad)); report["phones"].append(trio)
    for term, boxes in find_terms(words, a.terms):
        rects.append(union(boxes, pad)); report["terms"].append(term)
    for b in a.box:
        x0, y0, x1, y1 = map(float, b.split(","))
        rects.append((x0 * W, y0 * H, x1 * W, y1 * H))
    d = ImageDraw.Draw(img)
    for r in rects:
        d.rectangle(r, fill=(0, 0, 0))
    if img.width > MAX_W:
        img = img.resize((MAX_W, round(img.height * MAX_W / img.width)), Image.LANCZOS)
    y, m, dd = a.retrieved.split("-")
    note = "" if (a.keep_contacts and not a.terms and not a.box) else " · contact details redacted"
    img = stamp(img, f"Source: City of Boise Planning & Development Services, public case file {a.record} "
                     f"(permits.cityofboise.org) · retrieved {int(m)}/{int(dd)}/{y}{note}")
    img.save(a.out, quality=82, optimize=True)
    if a.preview:
        img.save(a.preview)
    missing = sorted(set(a.terms) - set(report["terms"]))
    report.update(out=a.out, rects=len(rects), terms_not_found=missing)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
