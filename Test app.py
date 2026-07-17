"""Regression test suite for the PDF Annotator.

Run all tests:      python test_app.py
Run one class:      python test_app.py TestPdfStore
Run one test:       python test_app.py TestPdfStore.test_corruption_stress_cycle

Runs headless — no display needed. Uses only the standard library (unittest),
so the project keeps its two-dependency footprint (PyQt6 + PyMuPDF).
"""
import os
import sys
import json
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fitz
from PyQt6.QtWidgets import QApplication, QDialog, QInputDialog, QFileDialog
from PyQt6.QtGui import QImage, QColor, QPainter
from PyQt6.QtCore import QPoint, Qt

# One QApplication for the whole run
_app = QApplication.instance() or QApplication(sys.argv[:1])

import main
import nodes as N
from pdf_store import PdfStore, rects_match


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_pdf(path, pages=4, text="hello world sample text for tests"):
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page()
        pg.insert_text((72, 100), f"page {i + 1} {text}")
        pg.insert_text((72, 140), "second line of the paragraph continues here")
    doc.save(path)
    doc.close()


def annot_types(path, page_idx):
    d = fitz.open(path)
    out = [a.type[0] for a in d[page_idx].annots()]
    d.close()
    return out


def image_count(path, page_idx):
    d = fitz.open(path)
    n = len(d[page_idx].get_images())
    d.close()
    return n


def fake_sketch_exec(self):
    img = QImage(100, 80, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setPen(QColor(0, 0, 0))
    p.drawLine(2, 2, 90, 70)
    p.end()
    self.result_image = img
    return QDialog.DialogCode.Accepted


class AppTestCase(unittest.TestCase):
    """Base: fresh temp dir, fresh window, fresh PDF, isolated settings."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="notetaker_test_")
        self._cwd = os.getcwd()
        os.chdir(self.tmp)  # settings/bookmarks JSON land here, not in the repo
        self.pdf_path = os.path.join(self.tmp, "doc.pdf")
        make_pdf(self.pdf_path)
        self.w = main.MainWindow()
        self.w.vault_path = os.path.join(self.tmp, "vault")
        os.makedirs(self.w.vault_path, exist_ok=True)

    def tearDown(self):
        try:
            for s in self.w.sessions.values():
                d = s.get("doc")
                if d is not None and not getattr(d, "is_closed", False):
                    d.close()
            if self.w.pdf.valid:
                self.w.pdf.doc.close()
        except Exception:
            pass
        self.w.deleteLater()
        os.chdir(self._cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # convenience
    def open_doc(self):
        self.w.open_pdf_path(self.pdf_path)
        self.w.save_to_pdf_mode = True

    def select(self, needle, page_idx=0):
        r = self.w.doc[page_idx].search_for(needle)
        self.assertTrue(r, f"'{needle}' not found on page {page_idx}")
        self.w.sel_page_idx = page_idx
        self.w.sel_offset = self.w.offset_of(page_idx) or 0
        self.w.current_selection_text = needle
        self.w.current_selection_fitz_rects = list(r)


# ── PdfStore ─────────────────────────────────────────────────────────────────

class TestPdfStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="store_test_")
        self.path = os.path.join(self.tmp, "s.pdf")
        make_pdf(self.path, pages=2)
        self.store = PdfStore()

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_open_valid(self):
        self.assertIsNotNone(self.store.open(self.path))
        self.assertTrue(self.store.valid)
        self.assertEqual(self.store.path, os.path.abspath(self.path))

    def test_open_missing_returns_none(self):
        self.assertIsNone(self.store.open(os.path.join(self.tmp, "nope.pdf")))

    def test_markup_write_and_save(self):
        self.store.open(self.path)
        r = self.store.doc[0].search_for("hello world")[0]
        self.assertTrue(self.store.add_markup(0, [r], "Underline", "Green"))
        self.store.save_now(force=True)
        self.assertIn(9, annot_types(self.path, 0))

    def test_save_disabled_blocks_writes(self):
        self.store.open(self.path)
        self.store.save_enabled = False
        r = self.store.doc[0].search_for("hello world")[0]
        self.assertFalse(self.store.add_markup(0, [r], "Highlight", "Yellow"))
        self.store.save_now(force=True)
        self.assertEqual(annot_types(self.path, 0), [])

    def test_remove_matching(self):
        self.store.open(self.path)
        r = self.store.doc[0].search_for("hello world")[0]
        self.store.add_markup(0, [r], "Highlight", "Yellow")
        node = N.markup_node("hello world", "highlight", 1,
                             [[r.x0, r.y0, r.x1, r.y1]], "Yellow", "Highlight")
        self.store.remove_matching(node)
        self.store.save_now(force=True)
        self.assertEqual(annot_types(self.path, 0), [])

    def test_corruption_stress_cycle(self):
        """add → save → delete → save → add → save must never corrupt the xref.
        This is the bug class that has bitten this project three times."""
        self.store.open(self.path)
        for _ in range(4):
            r = self.store.doc[0].search_for("hello world")[0]
            self.store.add_markup(0, [r], "Highlight", "Yellow")
            self.store.save_now(force=True)
            node = N.markup_node("hello world", "highlight", 1,
                                 [[r.x0, r.y0, r.x1, r.y1]], "Yellow", "Highlight")
            self.store.remove_matching(node)
            self.store.save_now(force=True)
        d = fitz.open(self.path)  # would raise / report 0 pages if corrupted
        self.assertEqual(len(d), 2)
        d.close()

    def test_sync_from_tree_backfills(self):
        self.store.open(self.path)
        r = self.store.doc[0].search_for("hello world")[0]
        tree = [N.markup_node("hello world", "highlight", 1,
                              [[r.x0, r.y0, r.x1, r.y1]], "Pink", "Highlight")]
        self.assertTrue(self.store.sync_from_tree(tree))
        self.store.save_now(force=True)
        self.assertIn(8, annot_types(self.path, 0))
        # second sync is a no-op (no duplicates)
        self.assertFalse(self.store.sync_from_tree(tree))

    def test_rects_match_rejects_neighbors(self):
        a = fitz.Rect(0, 0, 100, 10)
        neighbor = fitz.Rect(0, 12, 100, 22)   # adjacent line, no overlap
        touching = fitz.Rect(0, 9.5, 100, 20)  # tiny sliver of overlap
        self.assertFalse(rects_match(a, neighbor))
        self.assertFalse(rects_match(a, touching))
        self.assertTrue(rects_match(a, fitz.Rect(2, 1, 98, 9)))


# ── Nodes ────────────────────────────────────────────────────────────────────

class TestNodes(unittest.TestCase):
    def test_factories_have_required_fields(self):
        for n in [
            N.markup_node("t", "highlight", 1, [[0, 0, 1, 1]], "Yellow", "Highlight"),
            N.sticky_node("txt", 1, 5, 5, "Orange"),
            N.ink_node(1, [[0, 0], [1, 1]], [0, 0, 1, 1], "Red", 3),
            N.image_node("f.png", 1, fitz.Rect(0, 0, 1, 1), "Blue"),
            N.sketch_node("f.png", "/tmp/f.png", 1, fitz.Rect(0, 0, 1, 1), True),
        ]:
            for key in ("text", "custom_note", "role", "children", "page", "fitz_rects"):
                self.assertIn(key, n)

    def test_walk_and_remove(self):
        child = N.markup_node("c", "highlight", 1, [], "Yellow", "Highlight")
        parent = N.base_node("h", "h1", 1)
        parent["children"].append(child)
        tree = [parent]
        self.assertEqual(len(list(N.walk(tree))), 2)
        self.assertEqual(N.count_descendants(parent), 1)
        self.assertTrue(N.remove_node(tree, child))
        self.assertEqual(N.count_descendants(parent), 0)
        self.assertFalse(N.remove_node(tree, child))


# ── Annotations end-to-end ───────────────────────────────────────────────────

class TestAnnotations(AppTestCase):
    def test_highlight_roundtrip_all_styles(self):
        self.open_doc()
        style_type = {"Highlight": 8, "Underline": 9, "Squiggly": 10, "Strikeout": 11}
        for style, atype in style_type.items():
            self.w.markup_style = style
            self.select("hello world")
            self.w.add_annotation("highlight")
            self.w.pdf.save_now(force=True)
            self.assertIn(atype, annot_types(self.pdf_path, 0), style)
            self.w.delete_annotation(self.w.tree_widget.topLevelItem(0))
            self.assertNotIn(atype, annot_types(self.pdf_path, 0), style)

    def test_toggle_off_no_write_then_backfill(self):
        self.open_doc()
        self.w.save_to_pdf_mode = False
        self.select("hello world")
        self.w.add_annotation("highlight")
        self.w.pdf.save_now(force=True)
        self.assertEqual(annot_types(self.pdf_path, 0), [])
        self.w.save_to_pdf_mode = True
        self.w.sync_highlights_to_pdf()
        self.w.pdf.save_now(force=True)
        self.assertIn(8, annot_types(self.pdf_path, 0))

    def test_delete_cleans_even_with_toggle_off(self):
        self.open_doc()
        self.select("hello world")
        self.w.add_annotation("highlight")
        self.w.pdf.save_now(force=True)
        self.w.save_to_pdf_mode = False
        self.w.delete_annotation(self.w.tree_widget.topLevelItem(0))
        self.assertEqual(annot_types(self.pdf_path, 0), [])

    def test_recolor_updates_pdf(self):
        self.open_doc()
        self.w.auto_color = False
        self.w.highlight_color_name = "Green"
        self.w.markup_style = "Highlight"
        self.select("hello world")
        self.w.add_annotation("highlight")
        self.w.change_annotation_color(self.w.tree_widget.topLevelItem(0), "Pink")
        d = fitz.open(self.pdf_path)
        stroke = [a.colors["stroke"] for a in d[0].annots() if a.type[0] == 8][0]
        d.close()
        self.assertAlmostEqual(stroke[0], 0.96, places=1)

    def test_ink_roundtrip(self):
        self.open_doc()
        self.w.commit_ink_stroke([(100, 200), (150, 210), (200, 205)])
        self.w.pdf.save_now(force=True)
        self.assertIn(15, annot_types(self.pdf_path, 0))
        self.assertEqual(self.w.annotations[0]["role"], "ink")
        self.w.delete_annotation(self.w.tree_widget.topLevelItem(0))
        self.assertNotIn(15, annot_types(self.pdf_path, 0))

    def test_sticky_roundtrip(self):
        self.open_doc()
        orig = QInputDialog.getMultiLineText
        QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("note!", True))
        try:
            self.w.add_sticky_note(QPoint(100, 50))
        finally:
            QInputDialog.getMultiLineText = orig
        self.w.pdf.save_now(force=True)
        self.assertIn(0, annot_types(self.pdf_path, 0))
        self.w.delete_annotation(self.w.tree_widget.topLevelItem(0))
        self.assertNotIn(0, annot_types(self.pdf_path, 0))

    def test_sketch_sticky_lifecycle(self):
        self.open_doc()
        orig = main.SketchCanvasDialog.exec
        main.SketchCanvasDialog.exec = fake_sketch_exec
        try:
            # Place the sketch OVER the page text — deleting it must not eat the text
            self.w.add_sketch_sticky(QPoint(80, 95))
        finally:
            main.SketchCanvasDialog.exec = orig
        self.w.pdf.save_now(force=True)
        # Sketch stickies are overlay-only: the PNG lives in the vault and the
        # PDF is never touched (no embedded image, page text intact).
        self.assertEqual(image_count(self.pdf_path, 0), 0)
        sk = self.w.annotations[0]
        self.assertEqual(sk.get("role"), "sketch_sticky")
        self.assertTrue(os.path.exists(sk["img_path"]))
        # click toggles collapsed state (screen-px hit test)
        rc = sk["fitz_rects"][0]
        zf = self.w.zoom_factor
        pt = QPoint(int(rc[0] * zf) + 3, int(rc[1] * zf) + 3)
        was = sk["collapsed"]
        self.assertTrue(self.w.handle_sketch_click(pt))
        self.assertNotEqual(sk["collapsed"], was)
        # delete removes the node; the PDF stays pristine
        self.w.delete_annotation(self.w.tree_widget.topLevelItem(0))
        self.assertEqual(len(self.w.annotations), 0)
        d = fitz.open(self.pdf_path)
        self.assertIn("hello world", d[0].get_text())
        self.assertEqual(len(d[0].get_images()), 0)
        d.close()

    def test_sketch_png_is_opaque(self):
        """The real save path composites over white so sketches render everywhere
        (transparent PNGs were invisible in some PDF viewers)."""
        dlg = main.SketchCanvasDialog(None)
        dlg.draw_to(QPoint(10, 10))
        dlg.draw_to(QPoint(60, 60))
        dlg.end_stroke()
        dlg._on_save()
        self.assertIsNotNone(dlg.result_image)
        self.assertFalse(dlg.result_image.hasAlphaChannel())

    def test_text_sticky_expand_collapse(self):
        """Clicking a text sticky pin opens its note box; clicking again collapses."""
        self.open_doc()
        orig = QInputDialog.getMultiLineText
        QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("my note", True))
        try:
            self.w.add_sticky_note(QPoint(150, 150))
        finally:
            QInputDialog.getMultiLineText = orig
        n = self.w.annotations[0]
        rc = n["fitz_rects"][0]
        zf = self.w.zoom_factor
        pin = QPoint(int(rc[0] * zf) + 3, int(rc[1] * zf) + 3)
        self.assertTrue(self.w.handle_sketch_click(pin))
        self.assertFalse(n["collapsed"])
        # clicking inside the open note box collapses it again
        inside = QPoint(int(rc[0] * zf) + 60, int(rc[1] * zf) + 40)
        self.assertTrue(self.w.handle_sketch_click(inside))
        self.assertTrue(n["collapsed"])

    def test_eraser_deletes_ink_and_pins(self):
        self.open_doc()
        self.w.commit_ink_stroke([(100, 200), (150, 210), (200, 205)])
        orig = QInputDialog.getMultiLineText
        QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("n", True))
        try:
            self.w.add_sticky_note(QPoint(300, 60))
        finally:
            QInputDialog.getMultiLineText = orig
        self.w.eraser_action.setChecked(True)
        zf = self.w.zoom_factor
        # erase the ink stroke by clicking on it
        self.assertTrue(self.w.erase_at(QPoint(150, 210)))
        self.assertFalse(any(n["role"] == "ink" for n in self.w.annotations))
        # erase the sticky by clicking its pin
        n = self.w.annotations[0]
        rc = n["fitz_rects"][0]
        self.assertTrue(self.w.erase_at(QPoint(int(rc[0] * zf) + 3, int(rc[1] * zf) + 3)))
        self.assertEqual(len(self.w.annotations), 0)
        self.assertNotIn(15, annot_types(self.pdf_path, 0))
        self.assertNotIn(0, annot_types(self.pdf_path, 0))
        # empty click is a no-op
        self.assertFalse(self.w.erase_at(QPoint(5, 400)))
        self.w.eraser_action.setChecked(False)

    def test_pen_and_eraser_mutually_exclusive(self):
        self.open_doc()
        self.w.pen_action.setChecked(True); self.w.toggle_draw_mode(True)
        self.w.eraser_action.setChecked(True); self.w.toggle_eraser_mode(True)
        self.assertFalse(self.w.pen_action.isChecked())
        self.assertFalse(self.w.draw_mode)

    def test_area_capture_box(self):
        self.open_doc()
        self.w.screenshot_box = True
        self.w.capture_screenshot(QPoint(100, 100), QPoint(300, 250))
        self.w.pdf.save_now(force=True)
        self.assertIn(4, annot_types(self.pdf_path, 0))
        self.assertEqual(self.w.annotations[0]["role"], "image")


# ── Continuous scroll ────────────────────────────────────────────────────────

class TestContinuous(AppTestCase):
    def setUp(self):
        super().setUp()
        self.open_doc()
        self.w.continuous_action.setChecked(True)
        self.w.toggle_continuous_mode(True)
        self.w.current_page_idx = 1
        self.w.show_page()

    def test_window_and_offsets(self):
        pages = [p for p, _, _ in self.w.page_offsets]
        self.assertEqual(pages, [0, 1, 2])
        offs = [o for _, o, _ in self.w.page_offsets]
        self.assertEqual(offs, sorted(offs))

    def test_selection_on_other_page(self):
        off = self.w.offset_of(2)
        zf = self.w.zoom_factor
        self.w.begin_selection(QPoint(int(75 * zf), off + int(97 * zf)))
        self.assertEqual(self.w.sel_page_idx, 2)
        self.assertEqual(self.w.current_page_idx, 2)

    def test_word_and_block_select(self):
        off = self.w.offset_of(1)
        zf = self.w.zoom_factor
        pt = QPoint(int(75 * zf), off + int(97 * zf))
        self.w.select_word_at(pt)
        self.assertTrue(self.w.current_selection_text)
        one_word = self.w.current_selection_text
        self.w.select_block_at(pt)
        self.assertGreater(len(self.w.current_selection_text.split()),
                           len(one_word.split()))

    def test_scroll_follow_recenters(self):
        off2 = self.w.offset_of(2)
        self.w.on_viewer_scrolled(off2 + 10)
        self.assertEqual(self.w.current_page_idx, 2)
        self.assertIn(3, [p for p, _, _ in self.w.page_offsets])

    def test_annotation_lands_on_pressed_page(self):
        off = self.w.offset_of(2)
        zf = self.w.zoom_factor
        self.w.begin_selection(QPoint(int(75 * zf), off + int(97 * zf)))
        self.select("hello world", page_idx=2)
        self.w.add_annotation("highlight")
        self.w.pdf.save_now(force=True)
        self.assertEqual(self.w.annotations[0]["page"], 3)
        self.assertIn(8, annot_types(self.pdf_path, 2))


# ── Tabs / sessions ──────────────────────────────────────────────────────────

class TestTabs(AppTestCase):
    def test_open_switch_close(self):
        self.open_doc()
        second = os.path.join(self.tmp, "doc2.pdf")
        make_pdf(second, pages=1)
        self.w.open_pdf_path(second)
        self.assertEqual(self.w.doc_tabs.count(), 2)
        self.assertEqual(os.path.basename(self.w.pdf_path), "doc2.pdf")
        self.w.doc_tabs.setCurrentIndex(0)
        self.assertEqual(os.path.basename(self.w.pdf_path), "doc.pdf")
        self.assertTrue(self.w.pdf.valid)
        self.w.on_tab_close(1)
        self.assertEqual(self.w.doc_tabs.count(), 1)
        self.assertTrue(self.w.pdf.valid)

    def test_reopen_switches_not_duplicates(self):
        self.open_doc()
        self.w.open_pdf_path(self.pdf_path)
        self.assertEqual(self.w.doc_tabs.count(), 1)

    def test_annotations_stay_per_tab(self):
        self.open_doc()
        self.select("hello world")
        self.w.add_annotation("highlight")
        second = os.path.join(self.tmp, "doc2.pdf")
        make_pdf(second, pages=1)
        self.w.open_pdf_path(second)
        self.assertEqual(len(self.w.annotations), 0)
        self.w.doc_tabs.setCurrentIndex(0)
        self.assertEqual(len(self.w.annotations), 1)


# ── Exports & settings ───────────────────────────────────────────────────────

class TestExports(AppTestCase):
    def test_markdown_per_pdf(self):
        self.open_doc()
        self.select("hello world")
        self.w.add_annotation("highlight")
        md_files = [f for f in os.listdir(self.w.vault_path) if f.endswith(".md")]
        self.assertEqual(len(md_files), 1)
        content = open(os.path.join(self.w.vault_path, md_files[0]), encoding="utf-8").read()
        self.assertIn("hello world", content)

    def test_anki_export(self):
        self.open_doc()
        self.select("hello world")
        self.w.add_annotation("highlight")
        out = os.path.join(self.tmp, "cards.csv")
        orig = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out, ""))
        try:
            self.w.export_anki()
        finally:
            QFileDialog.getSaveFileName = orig
        rows = open(out, encoding="utf-8").read().strip().splitlines()
        self.assertEqual(len(rows), 1)
        self.assertIn("hello world", rows[0])

    def test_settings_roundtrip(self):
        self.open_doc()
        self.w.markup_style = "Underline"
        self.w.pen_color_name = "Blue"
        self.w.sketch_default_collapsed = False
        self.w.save_settings()
        data = json.load(open(os.path.join(self.tmp, main.MainWindow.SETTINGS_FILE)))
        self.assertEqual(data["markup_style"], "Underline")
        self.assertEqual(data["pen_color"], "Blue")
        self.assertFalse(data["sketch_default_collapsed"])

    def test_review_filter(self):
        self.open_doc()
        self.w.auto_color = False
        self.w.highlight_color_name = "Green"
        self.select("hello world")
        self.w.add_annotation("highlight")
        self.w.highlight_color_name = "Pink"
        self.select("sample text")
        self.w.add_annotation("highlight")
        self.w.review_color_filter.setCurrentText("All colors")
        self.assertEqual(self.w.review_list.topLevelItemCount(), 2)
        self.w.review_color_filter.setCurrentText("Pink")
        self.assertEqual(self.w.review_list.topLevelItemCount(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)