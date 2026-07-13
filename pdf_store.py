"""All PDF document I/O in one place.

PdfStore owns the fitz document and every write to it: opening (with auto
repair), debounced incremental saves, clean full saves (used after deletions,
which can corrupt the xref if saved incrementally), adding markup / ink /
sticky / image annotations, removing annotations matching a node, and syncing
the annotation tree into the PDF.

The `save_enabled` flag mirrors the UI's "Save highlights to PDF" toggle;
writes are skipped when it's off, but removal/full-save can be forced.
"""
import os
import fitz

from PyQt6.QtCore import QObject, QTimer

from theme import HIGHLIGHT_COLORS, PEN_COLORS
from nodes import walk

# Annot type numbers we manage (PDF spec): Text, Square, Highlight,
# Underline, Squiggly, StrikeOut, Ink
MANAGED_TYPES = (0, 4, 8, 9, 10, 11, 15)
MARKUP_TYPES = (8, 9, 10, 11)


def rects_match(a, b, threshold=0.5):
    """True if two rects overlap significantly (avoids matching mere neighbors)."""
    inter = fitz.Rect(a) & fitz.Rect(b)
    if inter.is_empty:
        return False
    min_area = min(abs(fitz.Rect(a)), abs(fitz.Rect(b)))
    return min_area > 0 and abs(inter) > threshold * min_area


class PdfStore(QObject):
    SAVE_DEBOUNCE_MS = 2000

    def __init__(self, parent=None, on_error=None):
        super().__init__(parent)
        self.doc = None
        self.path = ""
        self.save_enabled = True
        self._on_error = on_error or (lambda msg: print(msg))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(self.SAVE_DEBOUNCE_MS)
        self.timer.timeout.connect(self.save_now)

    # ── Lifecycle ────────────────────────────────────────────────────────────
    @property
    def valid(self):
        return self.doc is not None and not getattr(self.doc, "is_closed", False)

    def open(self, path):
        """Open a PDF, attempting pikepdf repair on corruption. Returns doc or None."""
        try:
            doc = fitz.open(path)
            if len(doc) == 0:
                raise ValueError("0 pages found, possible XREF corruption.")
        except Exception as e:
            print(f"Warning: PDF might be corrupted. Attempting auto-repair... ({e})")
            try:
                import pikepdf
                import shutil
                temp_path = path + ".repaired.pdf"
                with pikepdf.open(path) as pdf:
                    pdf.save(temp_path)
                shutil.move(temp_path, path)
                doc = fitz.open(path)
            except Exception as repair_e:
                print(f"Repair failed: {repair_e}")
                return None
        self.doc = doc
        self.path = os.path.abspath(path)
        return doc

    def adopt(self, doc, path):
        """Take ownership of an already-open document (tab switching)."""
        self.doc = doc
        self.path = path

    def release(self):
        """Give up ownership without closing (doc handed to a session)."""
        doc = self.doc
        self.doc = None
        self.path = ""
        return doc

    def close(self):
        self.flush()
        try:
            if self.valid:
                self.doc.close()
        except Exception:
            pass
        self.doc = None
        self.path = ""

    # ── Saving ───────────────────────────────────────────────────────────────
    def schedule_save(self):
        """Debounced incremental save — doesn't block the UI."""
        if not self.valid or not self.save_enabled:
            return
        self.timer.start()

    def flush(self):
        """If a debounced save is pending, run it now."""
        if self.timer.isActive():
            self.timer.stop()
            self.save_now()

    def save_now(self, force=False):
        """Incremental save; force=True does a clean full save (used after
        deletions — repeated saveIncr after annot deletion corrupts the xref)."""
        if not self.valid:
            return
        if not self.save_enabled and not force:
            return
        if force:
            self.full_save()
            return
        try:
            self.doc.saveIncr()
        except Exception as e:
            print(f"saveIncr failed: {e}")
            self.full_save()

    def full_save(self):
        """Rewrite the whole file cleanly (tmp + atomic swap), then reopen."""
        if not self.valid:
            return
        try:
            temp_path = self.path + ".tmp"
            self.doc.save(temp_path, incremental=False)
            self.doc.close()
            os.replace(temp_path, self.path)
            self.doc = fitz.open(self.path)
        except Exception as e2:
            print(f"Full save failed: {e2}")
            if getattr(self.doc, "is_closed", True):
                try:
                    self.doc = fitz.open(self.path)
                except Exception:
                    self.doc = None
                    self._on_error("⚠ PDF save failed. Reopen the PDF.")

    # ── Writing annotations ──────────────────────────────────────────────────
    def _markup_method(self, page, style):
        return {
            "Underline": page.add_underline_annot,
            "Strikeout": page.add_strikeout_annot,
            "Squiggly": page.add_squiggly_annot,
        }.get(style, page.add_highlight_annot)

    def add_markup(self, page_idx, rects, style, color_name):
        """Add highlight/underline/strikeout/squiggly annots; schedules a save."""
        if not (self.valid and self.save_enabled):
            return False
        page = self.doc[page_idx]
        add = self._markup_method(page, style)
        for r in rects:
            annot = add(r)
            if annot:
                annot.set_colors(stroke=HIGHLIGHT_COLORS[color_name])
                annot.update()
        self.schedule_save()
        return True

    def add_ink(self, page_idx, pdf_points, color_name, width):
        if not (self.valid and self.save_enabled):
            return False
        try:
            page = self.doc[page_idx]
            annot = page.add_ink_annot(
                [[(float(x), float(y)) for x, y in pdf_points]])
            if annot:
                annot.set_colors(stroke=PEN_COLORS[color_name])
                annot.set_border(width=width)
                annot.update()
            self.schedule_save()
            return True
        except Exception as e:
            print(f"Ink annot failed: {e}")
            return False

    def add_sticky(self, page_idx, x, y, text):
        if not (self.valid and self.save_enabled):
            return False
        try:
            page = self.doc[page_idx]
            annot = page.add_text_annot(fitz.Point(x, y), text)
            if annot:
                annot.update()
            self.schedule_save()
            return True
        except Exception as e:
            print(f"Sticky annot failed: {e}")
            return False

    def add_box(self, page_idx, rect, color_name, width=1.5):
        if not (self.valid and self.save_enabled):
            return False
        try:
            page = self.doc[page_idx]
            box = page.add_rect_annot(rect)
            if box:
                box.set_colors(stroke=HIGHLIGHT_COLORS[color_name])
                box.set_border(width=width)
                box.update()
            self.schedule_save()
            return True
        except Exception as e:
            print(f"Area box annot failed: {e}")
            return False

    def embed_image(self, page_idx, rect, filepath):
        """Embed a sketch image into the page. Returns the image xref (stored on
        the node so it can be replaced/blanked without using fragile rect-matching)."""
        if not self.valid:
            return None
        try:
            page = self.doc[page_idx]
            xref = page.insert_image(rect, filename=filepath)
            self.schedule_save()
            return xref
        except Exception as e:
            print(f"Sketch stamp failed: {e}")
            return None

    def update_image(self, page_idx, img_xref, new_filepath):
        """Replace an embedded sketch image in-place using its xref."""
        if not self.valid or not img_xref:
            return False
        try:
            page = self.doc[page_idx]
            pix = fitz.Pixmap(new_filepath)
            page.replace_image(img_xref, pixmap=pix)
            self.save_now(force=True)
            return True
        except Exception as e:
            print(f"Sketch update failed: {e}")
            return False

    def blank_image(self, page_idx, img_xref):
        """Replace a sketch image with a 1×1 white pixel (visually erases it
        without touching page text — redaction would wipe content underneath)."""
        if not self.valid or not img_xref:
            return False
        try:
            page = self.doc[page_idx]
            blank = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1, 1), False)
            blank.clear_with(255)
            page.replace_image(img_xref, pixmap=blank)
            self.save_now(force=True)
            return True
        except Exception as e:
            print(f"Sketch blank failed: {e}")
            return False

    # ── Removing ─────────────────────────────────────────────────────────────
    def remove_matching(self, node):
        """Remove PDF annots (and embedded sketch images) matching a node subtree."""
        if not self.valid:
            return
        for n in walk([node]):
            page_idx = n.get("page", 1) - 1
            if page_idx < 0 or page_idx >= len(self.doc):
                continue

            # Sketch stickies embed a real image — blank it using its stored xref.
            # blank_image replaces it with a 1×1 white pixel which is visually
            # invisible but preserves page text (unlike redaction which wipes content).
            if n.get("role") == "sketch_sticky":
                img_xref = n.get("img_xref")
                page_idx = n.get("page", 1) - 1
                if img_xref and 0 <= page_idx < len(self.doc):
                    self.blank_image(page_idx, img_xref)

            stored_rects = n.get("fitz_rects", [])
            text = n.get("text", "")
            target_rects = [fitz.Rect(sr) for sr in stored_rects if len(sr) == 4]
            if not target_rects and text and not text.startswith("![["):
                target_rects = self.doc[page_idx].search_for(text[:50])
            if not target_rects:
                continue

            # Delete one matching annot at a time, re-scanning after each
            keep_going = True
            while keep_going:
                keep_going = False
                page = self.doc[page_idx]
                try:
                    for annot in page.annots():
                        if annot.type[0] not in MANAGED_TYPES:
                            continue
                        if any(rects_match(annot.rect, tr) for tr in target_rects):
                            page.delete_annot(annot)
                            keep_going = True
                            break
                except Exception:
                    break

    def recolor_matching(self, node, color_name):
        """Update stroke color of markup annots matching a node; full save."""
        if not self.valid:
            return
        page_idx = node.get("page", 1) - 1
        rects = [fitz.Rect(r) for r in node.get("fitz_rects", []) if len(r) == 4]
        if not (0 <= page_idx < len(self.doc)) or not rects:
            return
        page = self.doc[page_idx]
        try:
            for annot in page.annots():
                if annot.type[0] not in MARKUP_TYPES:
                    continue
                if any(rects_match(annot.rect, r) for r in rects):
                    annot.set_colors(stroke=HIGHLIGHT_COLORS[color_name])
                    annot.update()
        except Exception:
            pass
        self.save_now(force=True)

    # ── Syncing ──────────────────────────────────────────────────────────────
    def sync_from_tree(self, annotations):
        """Add missing markup annots for every tree node. Returns True if changed."""
        if not self.valid:
            return False
        changed = False
        for n in walk(annotations):
            if n.get("sticky") or n.get("role") in ("image", "sketch_sticky", "ink"):
                continue
            page_idx = n.get("page", 1) - 1
            rects = [fitz.Rect(r) for r in n.get("fitz_rects", []) if len(r) == 4]
            if not rects or page_idx < 0 or page_idx >= len(self.doc):
                continue
            page = self.doc[page_idx]
            try:
                existing = [a.rect for a in page.annots() if a.type[0] in MARKUP_TYPES]
            except Exception:
                existing = []
            add = self._markup_method(page, n.get("style", "Highlight"))
            cname = n.get("color", "Yellow")
            for r in rects:
                if not any(rects_match(er, r) for er in existing):
                    annot = add(r)
                    if annot:
                        annot.set_colors(stroke=HIGHLIGHT_COLORS.get(
                            cname, HIGHLIGHT_COLORS["Yellow"]))
                        annot.update()
                        changed = True
        if changed:
            self.save_now()
        return changed