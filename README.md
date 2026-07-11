# PDF Annotator for Obsidian

A beautiful, lightweight, and highly customizable PDF annotator built specifically for seamless integration with Obsidian vaults. It allows you to read, highlight, annotate, and take screenshots of your PDFs, then automatically exports those annotations into perfectly formatted Markdown files inside your Obsidian vault.

## Features

- **Obsidian Integration:** Automatically saves annotations as Markdown directly in your Obsidian vault.
- **Save to PDF:** All highlights are optionally saved back to the original textbook PDF.
- **Robust Rendering:** Notes and highlights are securely drawn on screen directly from your Markdown data, meaning zero lagging and instant visual feedback, even if you turn off "Save to PDF".
- **Recent Files:** A quick-access menu showing your last 10 opened PDFs. Remove them with a single click if you want to clear your history!
- **Bookmarks:** The app automatically remembers the last page you were on for every PDF you open. Jump right back to where you left off.
- **Multiple Themes:** Choose from beautiful themes like Dark Black, Blue, Purple, and Sepia, along with a Night Mode toggle.
- **Rich Annotations:** Support for headers (H1-H4), highlights, text notes, and inline image snippets (screenshots).
- **Customizable Shortcuts:** Bind any tool to any key sequence through the built-in Interactive Shortcut Editor.
- **Session Restoration:** Load an existing Markdown annotation session and the app will automatically rebuild your annotation tree and highlight your PDF.
- **Table of Contents:** Quick navigation through the builtin PDF outline.

## Easy Setup for New Users

We provide a convenient script that automatically creates a Python virtual environment and installs all required dependencies.

1. **Clone or Download** this repository.
2. **Run `setup.bat`** (double-click it in Windows Explorer).
   - This will automatically create a `venv` and run `pip install -r requirements.txt`.
3. **Run the Application:**
   - Double-click **`Run PDF Annotator.bat`** to start the app.

*(If you are not on Windows, you can manually create a virtual environment, activate it, and run `pip install -r requirements.txt`, then run `python main.py`)*.

## How to Use

1. Click **📂 Open** to open a PDF file, or use the **Recent** button to pick up where you left off.
2. Click **⚙ Vault** to set your Obsidian vault directory (this is where annotations and screenshots are saved).
3. Select text in the PDF by clicking and dragging.
4. Use **Keyboard Shortcuts** (e.g. `Alt+1`, `Ctrl+Shift+V`) to create an annotation from the selected text.
5. Hit **F1** in the app to view the Cheatsheet of available keyboard shortcuts.

## Customizing Commands / Shortcuts

Keyboard shortcuts are fully customizable directly from the app interface!

1. Open the application.
2. Hit **F1** to open the Cheatsheet and Interactive Shortcut Editor.
3. Click on any shortcut box (e.g. `Alt+1`) and press your desired new keyboard combination on your keyboard (e.g. `Ctrl+H`).
4. Click **Save & Close** at the bottom. Your new shortcuts will take effect instantly and be saved for your next session!

## Requirements

The application requires Python 3.x and the packages listed in `requirements.txt`:
- `PyQt6` (for the GUI)
- `PyMuPDF` (for rendering and interacting with PDFs)
