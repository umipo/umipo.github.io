#!/usr/bin/env python3
"""
Builds the Personal Brands portfolio.

Usage:  python3 build.py            (run from inside the `site` folder, or anywhere)

For each student folder in the brands folder (see local.json) it:
  - finds the brand guide PDF, business card (PDF or PNGs), carousel (PDF or PNGs)
    and an optional logo (filename contains "logo" or "mark"; PNG/JPG/PDF) for the home grid
  - reads a Week 2 brand kit (filename contains "kit", "mood" or "brief"): a .docx table of
    image / link / annotation becomes a moodboard grid; a PDF kit is shown as pages
  - renders PDF pages to JPGs under site/assets/<slug>/
  - splits a single tall "stacked" carousel PDF into individual square slides
  - writes site/index.html from site/template.html (the data is inlined so the
    page works when opened directly from Finder, no server needed)

Optional per-student overrides: put a `brand.json` in the student's folder:
  { "name": "Display Name", "brand": "Brand title", "role": "what they do",
    "tagline": "one line", "words": ["Clean", "Curious"], "carouselTitle": "...",
    "credit": "Designed by ...", "links": {"Instagram": "https://..."},
    "accent": "#1f3fd1" (optional, auto-detected from the cover otherwise),
    "cover": "assets/<slug>/guide-01.jpg" (optional), "order": 3 (optional) }
"""
import io, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image

SITE = Path(__file__).resolve().parent
# Where the student folders live (one folder per student). Default: ../Personal Brands.
# Override with local.json next to this script: {"brandsDir": "../../../../Personal Brands"}
# (absolute, or relative to this script)
# (local.json is git-ignored, so the path to your Mac never reaches GitHub).
ROOT = SITE.parent / "Personal Brands"
_local = SITE / "local.json"
if _local.exists():
    ROOT = (SITE / Path(json.loads(_local.read_text(encoding="utf-8")).get("brandsDir", ROOT)).expanduser()).resolve()
ASSETS = SITE / "assets"
GUIDE_W, CARD_W, CAROUSEL_W = 1800, 1400, 1200
JPG_Q = 86

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def kind_of(name):
    n = name.lower()
    if "logo" in n or "mark" in n: return "logo"
    if "kit" in n or "mood" in n or "brief" in n: return "kit"
    if "card" in n: return "cards"
    if "carousel" in n or "instagram" in n or "insta" in n or "slides" in n: return "carousel"
    if n.endswith(".pdf") or n.endswith(".png") or n.endswith(".jpg") or n.endswith(".jpeg"): return "guide"
    return None

def render_pdf(pdf, out_dir, prefix, width):
    """Render every page of a PDF to JPGs. Returns list of relative paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp())
    subprocess.run(["pdftoppm", "-r", "200", "-png", str(pdf), str(tmpdir / prefix)], check=True)
    pages = sorted(tmpdir.glob(f"{prefix}-*.png"))
    paths = []
    for i, p in enumerate(pages, 1):
        im = Image.open(p).convert("RGB")
        if is_blank(im):
            print(f"   (skipping blank page {i} of {pdf.name})")
            continue
        paths += save_jpg(im, out_dir / f"{prefix}-{len(paths) + 1:02d}.jpg", width, out_dir)
    shutil.rmtree(tmpdir, ignore_errors=True)
    return paths

def split_stacked(im):
    """A very tall image = several slides stacked vertically (e.g. an Instagram
    carousel exported as one page, often with small labels between cards).
    Finds rows that are pure page-background (the gaps), keeps the tall
    segments as cards, and trims any title block sitting above the first card."""
    import numpy as np
    W, H = im.size
    small = im.convert("RGB").resize((200, max(1, int(H * 200 / W))), Image.BILINEAR)
    a = np.asarray(small).astype(np.int16)
    h, w, _ = a.shape
    scale = H / h
    bg = a[0, 0]
    gap = (np.abs(a - bg).sum(axis=2) < 40).mean(axis=1) > 0.99
    segs, start = [], None
    for y, g in enumerate(gap):
        if not g and start is None: start = y
        if g and start is not None: segs.append((start, y)); start = None
    if start is not None: segs.append((start, h))
    tall = [(s, e) for s, e in segs if (e - s) > 0.3 * w]
    if len(tall) < 2:
        n = round(H / W)                       # fallback: equal slices
        if n < 2: return [im]
        sh = H / n
        return [im.crop((0, int(k*sh), W, int((k+1)*sh))) for k in range(n)]
    heights = sorted(e - s for s, e in tall)
    card_h = heights[len(heights) // 2]        # typical card height
    out = []
    for s, e in tall:
        if e - s > card_h * 1.08:              # title/label block above the card
            s = e - card_h
        out.append(im.crop((0, int(s * scale), W, int(e * scale))))
    return out

def is_blank(im):
    """True when a rendered page is a single flat colour (an empty or broken page)."""
    small = im.convert("L").resize((64, 64))
    lo, hi = small.getextrema()
    return hi - lo < 8

def trim_letterbox(im):
    """Remove uniform bands (white letterboxing) left when a 16:9 artboard was
    exported onto an A4 page. Only trims when the band colour differs from the
    content behind it, so a white page with white margins is left alone."""
    import numpy as np
    W, H = im.size
    small = im.convert("RGB").resize((max(1, W // 4), max(1, H // 4)), Image.BILINEAR)
    a = np.asarray(small).astype(np.int16)
    h, w, _ = a.shape
    def band(axis, reverse):
        rows = a if axis == 0 else a.transpose(1, 0, 2)
        n = rows.shape[0]
        c = rows[-1 if reverse else 0, 0]
        k = 0
        order = range(n - 1, -1, -1) if reverse else range(n)
        for i in order:
            if (np.abs(rows[i] - c).sum(axis=1) < 24).mean() > 0.995: k += 1
            else:
                # look a few rows past the (anti-aliased) edge to see what the content is
                j = range(i - 4, i + 1) if reverse else range(i, i + 5)
                j = [x for x in j if 0 <= x < n]
                nxt = np.median(rows[j].reshape(-1, 3), axis=0)
                if np.abs(nxt - c).sum() < 40: k = 0     # same colour → margin, not a band
                break
        else:
            k = 0
        return k
    t, b_ = band(0, False), band(0, True)
    l, r = band(1, False), band(1, True)
    def ok(x, y, n): return x > 0.02 * n and y > 0.02 * n and min(x, y) / max(x, y) > 0.6
    box = [0, 0, W, H]
    if ok(t, b_, h): box[1], box[3] = t * 4, H - b_ * 4
    if ok(l, r, w): box[0], box[2] = l * 4, W - r * 4
    return im.crop(tuple(box)) if box != [0, 0, W, H] else im

def save_jpg(im, path, width, out_dir):
    out = []
    w, h = im.size
    pieces = split_stacked(im) if h > 2.5 * w else [trim_letterbox(im)]
    for j, piece in enumerate(pieces):
        target = path if len(pieces) == 1 else path.with_name(path.stem + f"-{j+1:02d}.jpg")
        pw, ph = piece.size
        if pw > width:
            piece = piece.resize((width, int(ph * width / pw)), Image.LANCZOS)
        piece.save(target, "JPEG", quality=JPG_Q, optimize=True, progressive=True)
        out.append(target.relative_to(SITE).as_posix())
    return out

def image_to_jpg(src, out_dir, prefix, idx, width):
    im = Image.open(src)
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    return save_jpg(im, out_dir / f"{prefix}-{idx:02d}.jpg", width, out_dir)

def dominant_colour(path):
    """Most common saturated colour on the cover page, as hex."""
    import numpy as np
    im = Image.open(path).convert("RGB").resize((64, 64))
    counts = {}
    for r, g, b in np.asarray(im).reshape(-1, 3).tolist():
        mx, mn = max(r, g, b), min(r, g, b)
        if mx - mn < 25 or mx > 245: continue     # skip greys / near-white
        key = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
        counts[key] = counts.get(key, 0) + 1
    if not counts: return "#333333"
    r, g, b = max(counts, key=counts.get)
    return "#%02x%02x%02x" % (r, g, b)

def moodboard_from_docx(path, out_dir):
    """Read a 'Build Your Brand Kit' Word file: every table row that holds a picture
    becomes one moodboard item (image, Pinterest link, the student's annotation in the
    last cell). Paragraphs outside tables are kept as the brand brief. Stdlib only."""
    import zipfile
    from xml.etree import ElementTree as ET
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    z = zipfile.ZipFile(path)
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("word/_rels/document.xml.rels"))}
    doc = ET.fromstring(z.read("word/document.xml"))
    items, brief = [], []
    n = 0
    for tr in doc.iter(W + "tr"):
        blips = [b.get(R + "embed") for b in tr.iter(A + "blip")]
        if not blips: continue
        cells = [" ".join((t.text or "") for t in c.iter(W + "t")).strip() for c in tr.findall(W + "tc")]
        links = [rels.get(h.get(R + "id"), "") for h in tr.iter(W + "hyperlink")]
        target = rels.get(blips[0], "")
        if not target: continue
        data = z.read(target if target.startswith("word/") else "word/" + target)
        n += 1
        im = Image.open(io.BytesIO(data))
        paths = image_to_jpg_im(im, out_dir / f"mood-{n:02d}.jpg", 900)
        items.append({"src": paths[0], "caption": cells[-1] if cells else "", "link": links[0] if links else ""})
    body = doc.find(W + "body")
    for p in body.findall(W + "p"):
        t = " ".join((x.text or "") for x in p.iter(W + "t")).strip()
        if t: brief.append(t)
    return items, brief

def image_to_jpg_im(im, path, width):
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    w, h = im.size
    if w > width:
        im = im.resize((width, int(h * width / w)), Image.LANCZOS)
    im.save(path, "JPEG", quality=JPG_Q, optimize=True, progressive=True)
    return [path.relative_to(SITE).as_posix()]

def save_logo(src, out_dir):
    """The student's mark, used on the home grid. PNG keeps transparency; a PDF
    uses its first page. Returns (path, background colour sampled from the corner,
    or "" when the corner is transparent)."""
    if src.suffix.lower() == ".pdf":
        tmpdir = Path(tempfile.mkdtemp())
        subprocess.run(["pdftoppm", "-r", "200", "-png", "-f", "1", "-l", "1", str(src), str(tmpdir / "logo")], check=True)
        im = Image.open(sorted(tmpdir.glob("logo*.png"))[0]).convert("RGBA")
        im = trim_letterbox(im.convert("RGB")).convert("RGBA")
    else:
        im = Image.open(src).convert("RGBA")
    w, h = im.size
    if max(w, h) > 1200:
        im = im.resize((int(w * 1200 / max(w, h)), int(h * 1200 / max(w, h))), Image.LANCZOS)
    out = out_dir / "logo.png"
    im.save(out, "PNG", optimize=True)
    r, g, b, a = im.getpixel((2, 2))
    bg = "#%02x%02x%02x" % (r, g, b) if a > 250 else ""
    return out.relative_to(SITE).as_posix(), bg

def build_student(folder):
    name = folder.name.replace("_", " ").strip()
    slug = slugify(name)
    out_dir = ASSETS / slug
    if out_dir.exists(): shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {}
    mp = folder / "brand.json"
    if mp.exists():
        meta = json.loads(mp.read_text())

    groups = {"guide": [], "cards": [], "carousel": [], "logo": [], "kit": []}
    def sort_key(f):
        n = f.name.lower()
        return (0 if "front" in n else 1 if "back" in n else 2, n)
    for f in sorted(folder.iterdir(), key=sort_key):
        if f.name.startswith(".") or f.name == "brand.json": continue
        k = kind_of(f.name)
        if k: groups[k].append(f)

    result = {"guide": [], "cards": [], "carousel": []}
    widths = {"guide": GUIDE_W, "cards": CARD_W, "carousel": CAROUSEL_W}
    logo, tile_bg = "", ""
    if groups["logo"]:
        logo, tile_bg = save_logo(groups["logo"][0], out_dir)
    moodboard, kit_pages, brief = [], [], []
    for f in groups["kit"]:
        if f.suffix.lower() == ".docx":
            m, b = moodboard_from_docx(f, out_dir)
            moodboard += m; brief += b
        elif f.suffix.lower() == ".pdf":
            kit_pages += render_pdf(f, out_dir, "kit", CARD_W)
        else:
            moodboard += [{"src": p, "caption": "", "link": ""} for p in image_to_jpg(f, out_dir, "mood", len(moodboard) + 1, 900)]
    for k, files in groups.items():
        if k in ("logo", "kit"): continue
        idx = 1
        for f in files:
            if f.suffix.lower() == ".pdf":
                paths = render_pdf(f, out_dir, k, widths[k])
                # rename to keep continuous numbering if several PDFs
                result[k] += paths
                idx += len(paths)
            else:
                result[k] += image_to_jpg(f, out_dir, k, idx, widths[k])
                idx += 1
    cover = meta.get("cover", result["guide"][0] if result["guide"] else (result["cards"][0] if result["cards"] else ""))
    accent = meta.get("accent") or tile_bg or (dominant_colour(SITE / cover) if cover else "#333333")
    return {
        "slug": slug,
        "name": meta.get("name", name),
        "brand": meta.get("brand", ""),
        "tagline": meta.get("tagline", ""),
        "credit": meta.get("credit", f"Designed by {meta.get('name', name)}"),
        "links": meta.get("links", {}),
        "order": meta.get("order", 999),
        "role": meta.get("role", ""),
        "words": meta.get("words", []),
        "carouselTitle": meta.get("carouselTitle", ""),
        "accent": accent,
        "logo": logo,
        "tileBg": meta.get("tileBg", tile_bg or accent),
        "moodboard": moodboard,
        "kitPages": kit_pages,
        "cover": cover,
        "guide": result["guide"],
        "cards": result["cards"],
        "carousel": result["carousel"],
    }

def main():
    students = []
    for folder in sorted(ROOT.iterdir()):
        if not folder.is_dir() or folder.name.startswith(".") or folder.name == "site": continue
        if not any(kind_of(f.name) for f in folder.iterdir() if f.is_file()): continue
        print(f"→ {folder.name}")
        students.append(build_student(folder))
    students.sort(key=lambda s: (s["order"], s["name"].lower()))
    data = json.dumps(students, indent=2, ensure_ascii=False)
    (SITE / "brands.js").write_text(
        "// Generated by build.py — do not edit by hand; edit brand.json in each student folder instead.\n"
        "window.BRANDS = " + data + ";\n", encoding="utf-8")
    template = (SITE / "template.html").read_text(encoding="utf-8")
    assert "/*__BRANDS__*/[]" in template, "template.html is missing the /*__BRANDS__*/[] placeholder"
    course_data = json.loads((SITE / "course.json").read_text(encoding="utf-8"))
    passcode = str(course_data.pop("passcode", "")).strip()
    pc_file = SITE / "passcode.txt"          # kept out of git; see .gitignore
    if pc_file.exists(): passcode = pc_file.read_text(encoding="utf-8").strip()
    if passcode:                     # only the hash goes into the page, never the passcode itself
        import hashlib
        course_data["passHash"] = hashlib.sha256(passcode.encode("utf-8")).hexdigest()
    course = json.dumps(course_data, indent=2, ensure_ascii=False)
    html = template.replace("/*__BRANDS__*/[]", data).replace("/*__COURSE__*/{}", course)
    (SITE / "index.html").write_text(html, encoding="utf-8")
    print(f"✓ {len(students)} students → index.html (open it in a browser)")

if __name__ == "__main__":
    main()
