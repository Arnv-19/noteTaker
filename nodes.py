"""Annotation node structure and tree helpers.

A node is a plain dict (kept JSON/markdown-friendly). All node creation goes
through the factories below so the schema lives in exactly one place.

Common fields (every node):
    text: str            display / exported text
    custom_note: str     user's own note (notes/stickies)
    role: str            h1|h2|h3|h4 | highlight | note | image | ink | sketch_sticky
    children: list       child nodes
    page: int            1-based page number
    fitz_rects: list     [[x0,y0,x1,y1], ...] in PDF coordinates

Role-specific fields:
    highlight/note: color (highlight color name), style (Highlight|Underline|Strikeout|Squiggly)
    note:           sticky (bool) marks a pinned sticky note
    ink:            pen_color, pen_width, ink_points [[x,y],...]
    image:          color (box outline color)
    sketch_sticky:  img_path, img_name, collapsed (bool), locked (bool)
"""

MARKUP_ROLES = ("highlight", "note")
HEADER_ROLES = ("h1", "h2", "h3", "h4")


def base_node(text, role, page, rects=None, custom_note=""):
    return {
        "text": text, "custom_note": custom_note, "role": role,
        "children": [], "page": page,
        "fitz_rects": rects or [],
    }


def markup_node(text, role, page, rects, color, style, custom_note=""):
    n = base_node(text, role, page, rects, custom_note)
    n["color"] = color
    n["style"] = style
    return n


def sticky_node(text, page, x, y, color):
    n = base_node(f"Sticky note (p.{page})", "note", page,
                  [[x, y, x + 9, y + 9]], custom_note=text)
    n["sticky"] = True
    n["color"] = color
    return n


def ink_node(page, points, bbox, pen_color, pen_width):
    n = base_node(f"Drawing (p.{page})", "ink", page, [bbox])
    n["pen_color"] = pen_color
    n["pen_width"] = pen_width
    n["ink_points"] = points
    return n


def image_node(filename, page, rect, color):
    n = base_node(f"![[attachments/{filename}]]", "image", page,
                  [[rect.x0, rect.y0, rect.x1, rect.y1]])
    n["color"] = color
    return n


def sketch_node(filename, filepath, page, rect, collapsed):
    n = base_node(f"![[attachments/{filename}]]", "sketch_sticky", page,
                  [[rect.x0, rect.y0, rect.x1, rect.y1]])
    n["img_path"] = filepath
    n["img_name"] = filename
    n["collapsed"] = collapsed
    n["locked"] = False
    return n


# ── Tree helpers ─────────────────────────────────────────────────────────────

def walk(nodes):
    """Yield every node in the tree, depth-first."""
    for n in nodes:
        yield n
        yield from walk(n.get("children", []))


def count_descendants(node):
    return len(node["children"]) + sum(count_descendants(c) for c in node["children"])


def remove_node(nodes, target):
    """Remove `target` (by identity) from the tree; returns True if found."""
    for i, n in enumerate(nodes):
        if n is target:
            nodes.pop(i)
            return True
        if remove_node(n["children"], target):
            return True
    return False


def all_ids(nodes):
    return {id(n) for n in walk(nodes)}