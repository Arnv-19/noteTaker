# PDF Annotator for Obsidian

A beautiful, lightweight, and highly customizable PDF annotator built specifically for seamless integration with Obsidian vaults. It allows you to read, highlight, annotate, and take screenshots of your PDFs, then automatically exports those annotations into perfectly formatted Markdown files inside your Obsidian vault.

## Features

- **Obsidian Integration:** Automatically saves annotations as Markdown directly in your Obsidian vault — one `.md` file per PDF.
- **PowerPoint Support:** Open `.pptx`/`.ppt` decks directly — they're auto-converted to a sibling `<name>.slides.pdf` (via installed MS PowerPoint, or LibreOffice as fallback) and every annotation feature works on the slides: text selection, highlights, markdown notes, pen, stickies. The converted PDF is cached and reused, so your annotations persist; the original deck is never modified. Requires PowerPoint or LibreOffice to be installed.
- **Multiple PDFs (Tabs):** Open several PDFs at once in tabs. Each tab keeps its own annotation tree, page position, and zoom; each exports to its own Markdown file.
- **Continuous Scroll:** Toggle 📜 for a smooth multi-page scrolling view, or keep classic single-page mode.
- **Save to PDF:** Highlights are optionally saved back into the PDF file. Turning the toggle ON backfills highlights made while it was off; deleting a note removes it from the PDF too.
- **Freehand Pen:** Draw directly on pages with a pressure-free ink tool (Red/Black/Blue/Green/White, adjustable thickness). Strokes save as real PDF ink annotations, render live, and can be erased individually or deleted from the tree.
- **Markup Styles:** Highlight, Underline, Strikeout, or Squiggly — pick from the toolbar.
- **Highlight Colors:** Yellow, Green, Pink, Blue, Orange. Optional auto color-coding by annotation type (configure per-type colors in Settings).
- **Sketch Stickies:** Drop a resizable drawing canvas on the page, sketch with pen + pixel eraser, and save. Saved sketches collapse to a small 🖌 icon (many can sit on one page without clutter) and expand on click. Each is embedded into the PDF as an image (visible in any reader), can be locked in place, and re-drawn later. Default collapsed/expanded state is configurable in Settings.
- **Sticky Notes:** Right-click anywhere on a page to pin a sticky note at that exact spot (saved as a real PDF text annotation).
- **Quick Selection:** Double-click selects a word, triple-click selects the whole paragraph.
- **Area Captures:** Screenshot a figure or diagram region — it's embedded in your Markdown and optionally boxed in the PDF.
- **Review Tab:** A flat list of every highlight and note, filterable by color — perfect for revision.
- **Anki Export:** One click exports your highlights and notes as an Anki-importable flashcard CSV.
- **Edit & Organize:** Edit annotation text/notes, recolor from the right-click menu, drag-and-drop to reorder, filter the tree, and clear per-page or all annotations.
- **Recent Files & Bookmarks:** Quick access to your last 10 PDFs; the app remembers your last page in every document.
- **Multiple Themes:** Dark Black, AMOLED (pure black), Blue, Purple, Sepia, plus Night Mode page inversion.
- **Rich Annotations:** Headers (H1-H4) with live child-count badges, highlights, notes, stickies, and image snippets.
- **Customizable Shortcuts:** Bind any tool to any key sequence through the built-in Shortcut Editor.
- **Session Restoration:** Load an existing Markdown session to rebuild your annotation tree.
- **Markdown Viewer:** Open and read any `.md` note from your Obsidian vault as formatted rich text — headings, quotes, notes, and embedded images render inline (no PDF required).
- **Markdown Editor (Obsidian-style):** Create and edit `.md` notes with a live split-screen preview. Embed images **and video** exactly like Obsidian — drop a file in via 🖼/🎬 (it's copied into `attachments/` and linked as `![[...]]`), and it renders inline in the preview, with video playing right in the note. The preview matches your active theme.
- **Notes Sidebar (no vault required):** Toggle 🗂 to show a collapsible sidebar. Click 📂 inside it to browse **any folder** — your Obsidian vault, a downloads folder, a lectures folder — no vault setup needed. It lists `.md` notes **and media** (🎬 video, 🎵 audio, 🖼 images). Click a note to edit it; click a lecture video to play it right there. Remembered between sessions.
- **Editor Formatting Shortcuts:** In the note editor, type text, select it, and press the app's own heading keys (`Alt+1`–`Alt+4` by default, customizable in the Shortcut Editor) to make it H1–H4 — press again to toggle off. Plus `Ctrl+B` bold, `Ctrl+I` italic, `Ctrl+Shift+Q` quote, `Ctrl+Shift+L` bullet list, and `Ctrl+E` to flip between edit and preview, just like Obsidian. Toolbar buttons (H1–H4, 𝐁, 𝘐, ❝, •) do the same by mouse.
- **Table of Contents:** Quick navigation through the built-in PDF outline.

## Easy Setup for New Users

We provide a convenient script that automatically creates a Python virtual environment and installs all required dependencies.

1. **Clone or Download** this repository.
2. **Run `setup.bat`** (double-click it in Windows Explorer).
   - This creates a `venv`, upgrades `pip`, and runs `pip install -r requirements.txt`.
   - The first run downloads `PyQt6-WebEngine` (used for the Markdown note preview), which is large — it may take a few minutes.
3. **Run the Application:**
   - Double-click **`Run PDF Annotator.bat`** to start the app.

> **Updating?** If you already had the app set up before the Markdown-notes features were added, just **re-run `setup.bat`** to install the new `PyQt6-WebEngine` dependency.

*(If you are not on Windows, you can manually create a virtual environment, activate it, and run `pip install -r requirements.txt`, then run `python main.py`)*.

## How to Use

1. Click **📂 Open** to open a PDF file, or use the **Recent** button to pick up where you left off.
2. Click **⚙ Vault** to set your Obsidian vault directory (this is where annotations and screenshots are saved).
3. Select text in the PDF by clicking and dragging.
4. Use **Keyboard Shortcuts** (e.g. `Alt+1`, `Ctrl+Shift+V`) to create an annotation from the selected text.
5. Hit **F1** in the app to view the Cheatsheet of available keyboard shortcuts.

### Working with Markdown Notes (Obsidian-style)

1. Toggle the **🗂 Notes sidebar** and click **📂** to browse any folder — an Obsidian vault is *optional*. (If you have set a vault, the sidebar shows it by default.)
2. **Click a note** to open it in the editor, a **🎬 video / 🎵 audio / 🖼 image** to open it in the built-in player — handy for downloaded lectures. Or use **📝 New Markdown Note** / **✏ Edit Markdown Note** from the File menu.
3. In the editor, write Markdown on the left and see a **live preview** on the right (**Split / Editor / Preview**, or `Ctrl+E` to flip edit↔preview).
4. **Format like Obsidian:** select text and press `Alt+1`–`Alt+4` for headings (your customized app shortcuts apply here too), `Ctrl+B` bold, `Ctrl+I` italic, `Ctrl+Shift+Q` quote, `Ctrl+Shift+L` list — or use the toolbar buttons.
5. Use the **🖼 Image** and **🎬 Video** buttons to embed media — the file is copied into `attachments/` and linked as `![[...]]`. Images render inline and **video plays right inside the note**.
6. **📖 Open Markdown File** gives a quick, lightweight read-only view of any `.md` file.

## Customizing Commands / Shortcuts

Keyboard shortcuts are fully customizable directly from the app interface!

1. Open the application.
2. Hit **F1** to open the Cheatsheet and Interactive Shortcut Editor.
3. Click on any shortcut box (e.g. `Alt+1`) and press your desired new keyboard combination on your keyboard (e.g. `Ctrl+H`).
4. Click **Save & Close** at the bottom. Your new shortcuts will take effect instantly and be saved for your next session!

## Requirements

The application requires Python 3.x and the packages listed in `requirements.txt`:
- `PyQt6` (for the GUI)
- `PyQt6-WebEngine` (for the Obsidian-style Markdown note preview with inline images & video)
- `PyMuPDF` (for rendering and interacting with PDFs)
- `pikepdf` (for the PDF repair / structural rebuild tool, `repair.py`)


## Architecture

The codebase is split into focused modules:

| Module | Responsibility |
|---|---|
| `main.py` | MainWindow: UI wiring, annotation tree, tabs, exports |
| `pdf_store.py` | **All** PDF I/O: open/auto-repair, debounced & full saves, annotation writes, removal, tree sync |
| `viewer.py` | The page viewer widget: text selection, ink strokes, sketch-sticky clicks |
| `sketch.py` | The Sketch Sticky drawing canvas (pen + pixel eraser) |
| `nodes.py` | Annotation node schema, factories, and tree helpers |
| `theme.py` | Themes, color palettes, and the global stylesheet |
| `widgets.py` | Small reusable widgets |

Run with `python main.py` as before.


## Testing & Maintenance

- **`python test_app.py`** — full regression suite (34 tests, ~2s, headless, stdlib unittest only). Run before committing changes.
- **`python repair.py <file.pdf>`** — PDF doctor: detects xref corruption and silent structural damage, rebuilds via pikepdf with a `.bak` backup. Add `--check` to inspect without modifying.
- **`python repair.py --vault [--fix]`** — vault doctor: finds notes referencing missing attachment images, orphaned attachments, and stale bookmarks. `--fix` quarantines orphans into `attachments/_orphaned/`.