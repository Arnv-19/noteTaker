"""PDF & Vault Doctor for the PDF Annotator.

Usage:
    python repair.py <file.pdf>              Check a PDF's health; repair if broken
    python repair.py <file.pdf> --check      Check only, never modify
    python repair.py --vault [path]          Audit the vault (settings, markdown
                                             attachments, bookmarks); report issues
    python repair.py --vault [path] --fix    Also move orphaned attachment images
                                             into attachments/_orphaned/

PDF repair uses pikepdf (QPDF) and always writes the repaired copy to a temp
file first — the original is only replaced after the repaired file verifies.
A .bak of the original is kept next to it.
"""
import os
import sys
import json
import shutil

import fitz

SETTINGS_FILE = "annotator_settings.json"


# ── PDF doctor ───────────────────────────────────────────────────────────────

def check_pdf(path):
    """Return (ok: bool, report: list[str]). Never modifies the file."""
    report = []
    if not os.path.exists(path):
        return False, [f"File not found: {path}"]
    size = os.path.getsize(path)
    report.append(f"Size: {size / 1024 / 1024:.2f} MB")

    try:
        doc = fitz.open(path)
    except Exception as e:
        return False, report + [f"❌ Cannot open: {e}"]

    try:
        n_pages = len(doc)
        if n_pages == 0:
            return False, report + ["❌ 0 pages — likely xref corruption"]
        report.append(f"Pages: {n_pages}")

        repaired = bool(getattr(doc, "is_repaired", False))
        if repaired:
            report.append("⚠ Structural damage detected — MuPDF repaired it in "
                          "memory. The file on disk is still damaged.")

        n_annots, bad_annots = 0, 0
        n_images = 0
        for page in doc:
            try:
                for a in page.annots():
                    n_annots += 1
                    _ = a.rect, a.type  # touching these surfaces malformed annots
            except Exception:
                bad_annots += 1
            try:
                n_images += len(page.get_images())
            except Exception:
                pass
        report.append(f"Annotations: {n_annots}"
                      + (f" (⚠ {bad_annots} page(s) with malformed annots)" if bad_annots else ""))
        report.append(f"Embedded images: {n_images}")

        # xref sanity: try a full in-memory rewrite
        try:
            doc.tobytes()
            report.append("XREF: ✓ clean full rewrite possible")
            healthy = bad_annots == 0 and not repaired
        except Exception as e:
            report.append(f"XREF: ❌ rewrite failed ({e})")
            healthy = False
    finally:
        doc.close()
    return healthy, report


def repair_pdf(path):
    """Repair via pikepdf. Verifies the result before replacing the original.
    Keeps a .bak of the original. Returns True on success."""
    try:
        import pikepdf
    except ImportError:
        print("❌ pikepdf is not installed. Install it with:")
        print("   pip install pikepdf")
        return False

    tmp = path + ".repaired.tmp"
    try:
        print("Rebuilding with pikepdf/QPDF ...")
        with pikepdf.open(path) as pdf:
            pdf.save(tmp)
        # Verify the repaired file actually opens with a sane page count
        d = fitz.open(tmp)
        pages = len(d)
        d.close()
        if pages == 0:
            raise ValueError("repaired file has 0 pages")
        bak = path + ".bak"
        shutil.copy2(path, bak)
        os.replace(tmp, path)
        print(f"✓ Repaired ({pages} pages). Original backed up to {os.path.basename(bak)}")
        return True
    except Exception as e:
        print(f"❌ Repair failed: {e}")
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


# ── Vault doctor ─────────────────────────────────────────────────────────────

def _load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return None, f"No {SETTINGS_FILE} in current directory (run from the app folder)"
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, f"❌ {SETTINGS_FILE} is not valid JSON: {e}"


def audit_vault(vault_path=None, fix=False):
    issues = 0
    settings, err = _load_settings()
    if err:
        print(err)
        if settings is None and vault_path is None:
            return 1
    if vault_path is None:
        vault_path = (settings or {}).get("vault_path", "")
    if not vault_path or not os.path.isdir(vault_path):
        print(f"❌ Vault folder not found: {vault_path!r}")
        return 1
    print(f"Vault: {vault_path}\n")

    # 1. Collect attachment references from every markdown file
    referenced = set()
    md_files = [f for f in os.listdir(vault_path) if f.endswith(".md")]
    print(f"Markdown files: {len(md_files)}")
    for fname in md_files:
        try:
            with open(os.path.join(vault_path, fname), encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"  ⚠ Cannot read {fname}: {e}")
            issues += 1
            continue
        start = 0
        while True:
            i = content.find("![[attachments/", start)
            if i < 0:
                break
            j = content.find("]]", i)
            if j < 0:
                break
            referenced.add(content[i + len("![[attachments/"):j])
            start = j + 2

    # 2. Missing attachments (referenced but file gone)
    att_dir = os.path.join(vault_path, "attachments")
    existing = set(os.listdir(att_dir)) if os.path.isdir(att_dir) else set()
    missing = sorted(referenced - existing)
    if missing:
        print(f"\n❌ {len(missing)} referenced attachment(s) missing from attachments/:")
        for m in missing:
            print(f"   - {m}")
        issues += len(missing)
    else:
        print(f"Attachments referenced: {len(referenced)} — all present ✓")

    # 3. Orphaned attachments (file exists, nothing references it)
    orphans = sorted(f for f in existing
                     if f not in referenced and not f.startswith("_")
                     and f.lower().endswith((".png", ".jpg", ".jpeg")))
    if orphans:
        print(f"\n⚠ {len(orphans)} orphaned attachment(s) (on disk, referenced by no note):")
        for o in orphans:
            print(f"   - {o}")
        if fix:
            dest = os.path.join(att_dir, "_orphaned")
            os.makedirs(dest, exist_ok=True)
            for o in orphans:
                shutil.move(os.path.join(att_dir, o), os.path.join(dest, o))
            print(f"   → moved to attachments/_orphaned/ (delete when sure)")
        else:
            print("   (re-run with --fix to move them into attachments/_orphaned/)")

    # 4. Bookmarks / recent files pointing at moved PDFs
    if settings:
        stale = [p for p in (settings.get("recent_files") or []) if not os.path.exists(p)]
        stale += [p for p in (settings.get("bookmarks") or {}) if not os.path.exists(p)]
        stale = sorted(set(stale))
        if stale:
            print(f"\n⚠ {len(stale)} setting entr(ies) point at PDFs that no longer exist:")
            for s in stale:
                print(f"   - {s}")
            print("   (harmless — the app skips them — but you can clean Recent Files in-app)")

    print(f"\n{'✓ Vault healthy' if issues == 0 else f'{issues} issue(s) found'}")
    return 0 if issues == 0 else 1


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    if args[0] == "--vault":
        path = None
        rest = args[1:]
        if rest and not rest[0].startswith("-"):
            path = rest[0]
        return audit_vault(path, fix="--fix" in args)

    path = args[0]
    check_only = "--check" in args
    ok, report = check_pdf(path)
    print(f"Checking: {path}")
    for line in report:
        print(f"  {line}")
    if ok:
        print("✓ PDF is healthy — no repair needed.")
        return 0
    if check_only:
        print("Run without --check to attempt repair.")
        return 1
    print()
    return 0 if repair_pdf(path) else 1


if __name__ == "__main__":
    sys.exit(main())