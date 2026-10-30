"""Inventory exam submissions: render pages, hash files, read metadata, find look-alikes.

Usage: python -I prepare.py <submissions_dir> <work_dir> [--dpi 110] [--max-side 1400]
Needs: pymupdf, pillow. Never writes into submissions_dir.
"""
import argparse
import csv
import hashlib
import itertools
import re
from pathlib import Path

import fitz
from PIL import ExifTags, Image, ImageOps

NAME = re.compile(r"_(?P<student>\d{6,})_attempt_(?P<attempt>[\d-]+)_(?P<label>.*)$")
IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".tif", ".tiff"}
HASH_THRESHOLD = 10  # out of 256 bits; lower is more alike


def dhash(img, size=16):
    gray = ImageOps.autocontrast(img.convert("L")).resize((size + 1, size))
    px = list(gray.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            bits = bits << 1 | (px[row * (size + 1) + col] > px[row * (size + 1) + col + 1])
    return bits


def image_meta(img):
    wanted = {"DateTime", "DateTimeOriginal", "Make", "Model", "Software"}
    exif = img.getexif()
    tags = dict(exif)
    tags.update(exif.get_ifd(0x8769))
    found = {ExifTags.TAGS.get(k, k): v for k, v in tags.items()}
    return "; ".join(f"{k}={found[k]}" for k in sorted(wanted & found.keys()))


def pdf_meta(doc):
    keep = ("creator", "producer", "creationDate", "modDate", "author", "title")
    return "; ".join(f"{k}={doc.metadata[k]}" for k in keep if doc.metadata and doc.metadata.get(k))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("submissions")
    ap.add_argument("work")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--max-side", type=int, default=1400)
    args = ap.parse_args()
    root, work = Path(args.submissions), Path(args.work)
    (work / "pages").mkdir(parents=True, exist_ok=True)

    rows, hashes = [], []
    counters = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        m = NAME.search(path.stem + path.suffix)
        student = m["student"] if m else "unknown"
        attempt = m["attempt"] if m else ""
        label = m["label"] if m else path.name
        question = path.parent.name
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        meta, images, text_chars, error = "", [], 0, ""
        try:
            if path.suffix.lower() == ".pdf":
                doc = fitz.open(path)
                meta = pdf_meta(doc)
                for page in doc:
                    text_chars += len(page.get_text().strip())
                    pix = page.get_pixmap(dpi=args.dpi, alpha=False)
                    images.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
            elif path.suffix.lower() in IMAGES:
                img = Image.open(path)
                meta = image_meta(img)
                images.append(ImageOps.exif_transpose(img).convert("RGB"))
            else:
                error = "unsupported type"
        except Exception as exc:  # corrupt uploads are a finding, not a crash
            error = str(exc)

        out_dir = work / "pages" / student
        out_dir.mkdir(exist_ok=True)
        for img in images:
            counters[student] = counters.get(student, 0) + 1
            img.thumbnail((args.max_side, args.max_side))
            out = out_dir / f"{question}_{counters[student]:02d}.jpg"
            img.save(out, quality=80)
            hashes.append((student, str(out.relative_to(work)), dhash(img)))
        rows.append(dict(student=student, question=question, attempt=attempt, label=label,
                         file=str(path.relative_to(root)), bytes=path.stat().st_size, sha256=sha,
                         pages=len(images), embedded_text_chars=text_chars, metadata=meta, error=error))

    with open(work / "manifest.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    by_hash = {}
    for r in rows:
        by_hash.setdefault(r["sha256"], []).append(r)
    with open(work / "same_file_across_students.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["sha256", "students", "files"])
        for sha, group in by_hash.items():
            if len({r["student"] for r in group}) > 1:
                w.writerow([sha, " | ".join(sorted({r["student"] for r in group})),
                            " | ".join(r["file"] for r in group)])

    pairs = []
    for (s1, p1, h1), (s2, p2, h2) in itertools.combinations(hashes, 2):
        if s1 != s2:
            dist = bin(h1 ^ h2).count("1")
            if dist <= HASH_THRESHOLD:
                pairs.append((dist, s1, p1, s2, p2))
    with open(work / "similar_pages.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["hash_distance", "student_a", "page_a", "student_b", "page_b"])
        w.writerows(sorted(pairs))

    print(f"students={len({r['student'] for r in rows})} files={len(rows)} pages={len(hashes)} "
          f"errors={sum(bool(r['error']) for r in rows)} similar_pairs={len(pairs)}")


if __name__ == "__main__":
    main()
