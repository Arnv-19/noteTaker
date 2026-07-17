"""PowerPoint → PDF conversion so slide decks can ride the existing PDF pipeline.

Slides are converted once to a sibling `<name>.slides.pdf` and reused on later
opens (re-converted only if the .pptx is newer). All annotation features then
work on the converted PDF: text selection, highlights, markdown notes, pen,
stickies. Note: annotations live in the converted PDF, NOT in the original
.pptx — the original deck is never modified.

Conversion backends, tried in order:
  1. Microsoft PowerPoint via COM automation (PowerShell, no extra pip deps)
  2. LibreOffice (`soffice --headless --convert-to pdf`)
Both keep real selectable text in the output.
"""
import os
import shutil
import subprocess

PPT_EXTS = (".ppt", ".pptx", ".pps", ".ppsx")


def is_ppt(path):
    return os.path.splitext(path)[1].lower() in PPT_EXTS


def converted_pdf_path(ppt_path):
    base, _ = os.path.splitext(os.path.abspath(ppt_path))
    return base + ".slides.pdf"


def _convert_via_powerpoint(ppt_path, out_path):
    """Use installed MS PowerPoint through COM (PowerShell). Raises on failure."""
    ppt_path = ppt_path.replace("'", "''")
    out_path = out_path.replace("'", "''")
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "$pp = New-Object -ComObject PowerPoint.Application; "
        "try { "
        f"$pres = $pp.Presentations.Open('{ppt_path}', $true, $true, $false); "
        f"$pres.SaveAs('{out_path}', 32); "  # 32 = ppSaveAsPDF
        "$pres.Close() "
        "} finally { $pp.Quit() }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True, capture_output=True, timeout=180,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if not os.path.exists(out_path):
        raise RuntimeError("PowerPoint reported success but no PDF was produced")


def _convert_via_libreoffice(ppt_path, out_path):
    """Use LibreOffice headless conversion. Raises on failure."""
    soffice = shutil.which("soffice") or shutil.which("soffice.exe")
    if not soffice:
        for cand in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                     r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
            if os.path.exists(cand):
                soffice = cand
                break
    if not soffice:
        raise FileNotFoundError("LibreOffice (soffice) not found")
    out_dir = os.path.dirname(out_path)
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, ppt_path],
        check=True, capture_output=True, timeout=300,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    # soffice names the output <base>.pdf; move it to our .slides.pdf name
    produced = os.path.join(out_dir, os.path.splitext(os.path.basename(ppt_path))[0] + ".pdf")
    if not os.path.exists(produced):
        raise RuntimeError("LibreOffice reported success but no PDF was produced")
    if os.path.abspath(produced) != os.path.abspath(out_path):
        shutil.move(produced, out_path)


def convert_ppt_to_pdf(ppt_path):
    """Convert a PowerPoint file to PDF, caching the result next to it.

    Returns the PDF path, or None if no converter is available/working.
    A cached PDF is reused unless the source deck is newer (so annotations
    made on the PDF survive across sessions).
    """
    ppt_path = os.path.abspath(ppt_path)
    out_path = converted_pdf_path(ppt_path)
    if os.path.exists(out_path) and os.path.getmtime(out_path) >= os.path.getmtime(ppt_path):
        return out_path

    errors = []
    for backend in (_convert_via_powerpoint, _convert_via_libreoffice):
        try:
            backend(ppt_path, out_path)
            return out_path
        except Exception as e:
            errors.append(f"{backend.__name__}: {e}")
    print("PPT conversion failed:\n  " + "\n  ".join(errors))
    return None
