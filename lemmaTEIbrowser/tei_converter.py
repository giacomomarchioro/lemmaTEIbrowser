"""
tei_converter.py
----------------
Converts a TEI XML tree (already parsed) into a self-contained HTML string.
No file I/O: callers own reading and writing.

Public API
----------
    convert_tree(root: lxml.etree._Element, text_id: int | str) -> str
    convert_file(path: Path | str, text_id: int | str) -> str   # convenience
"""

from __future__ import annotations
from lxml import etree

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _local(el) -> str:
    """Tag name without namespace prefix."""
    t = el.tag
    return t.split("}")[-1] if "}" in t else t


def _xml_id(el) -> str:
    return el.get(f"{{{XML_NS}}}id") or el.get("xml:id", "")


def _el_to_html(el) -> str:
    """Recursively serialise a TEI element to an HTML fragment.

    Tail text is always emitted *outside* the wrapping tag so inter-word
    whitespace / punctuation stays in the flow.
    """
    t = _local(el)
    tail = el.tail or ""

    # <w> → <span class="w" id="…">
    if t == "w":
        wid = _xml_id(el)
        id_attr = f' id="{wid}"' if wid else ""
        inner = (el.text or "") + "".join(_el_to_html(c) for c in el)
        return f'<span class="w"{id_attr}>{inner}</span>{tail}'

    # <head> → <h2>  (multiple <head> inside one <div> are all h2)
    if t == "head":
        inner = (el.text or "") + "".join(_el_to_html(c) for c in el)
        return f"<h2>{inner}</h2>{tail}"

    # <p> / <ab> → <p>
    if t in ("p", "ab"):
        inner = (el.text or "") + "".join(_el_to_html(c) for c in el)
        return f"<p>{inner}</p>{tail}"

    # <div> → <section class="div-TYPE">
    if t == "div":
        dtype = el.get("type", "")
        cls = f'div-{dtype}' if dtype else "div"
        inner = (el.text or "") + "".join(_el_to_html(c) for c in el)
        return f'<section class="{cls}">{inner}</section>{tail}'

    # <lb> → <br>
    if t == "lb":
        return f"<br>{tail}"

    # Everything else: recurse, preserving text
    inner = (el.text or "") + "".join(_el_to_html(c) for c in el)
    return inner + tail


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="stylesheet" href="/static/css/text.css">
</head>
<body>
<header class="text-header">
  <p class="text-id">text:{text_id}</p>
  <h1>{title}</h1>
  <p class="text-author">{author}</p>
  <p class="text-date">{date}</p>
</header>
<main class="text-body">
{body}
</main>
<script>
/* Highlight + scroll to a word via ?w=WORD_XML_ID */
(function () {{
  var params = new URLSearchParams(window.location.search);
  var wid = params.get("w");
  if (!wid) return;
  var target = document.getElementById(wid);
  if (!target) return;
  target.classList.add("w--highlight");
  target.scrollIntoView({{ behavior: "smooth", block: "center" }});
}})();
</script>
</body>
</html>
"""

# Minimal bundled fallback CSS (used only when the link above 404s)
# Real apps should put this in static/css/text.css
BUNDLED_CSS = """
body{max-width:800px;margin:2rem auto;padding:0 1.5rem;font-family:Georgia,serif;
     line-height:1.8;color:#1a1a1a}
.text-header{border-bottom:1px solid #ccc;margin-bottom:2rem;padding-bottom:.75rem}
.text-header h1{margin:.25rem 0}
.text-author,.text-date,.text-id{margin:.1rem 0;color:#666;font-style:italic;font-size:.9rem}
section{margin-bottom:2.5rem}
h2{font-size:.95rem;text-transform:uppercase;letter-spacing:.07em;margin-bottom:.3rem}
span.w{cursor:pointer}
span.w:target,span.w.w--highlight{
  background:#ffe08a;border-radius:2px;outline:2px solid #f0b429}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert_tree(root, text_id: int | str, *, embed_css: bool = False) -> str:
    """Convert an already-parsed lxml element tree root to HTML.

    Parameters
    ----------
    root:       lxml _Element for the <TEI> root
    text_id:    The database id of the TextEntry (used in the page header)
    embed_css:  If True, inline the bundled CSS instead of linking /static/css/text.css
                Useful for completely standalone files.
    """
    ns = {"t": TEI_NS}

    def _one(xpath, default=""):
        nodes = root.xpath(xpath, namespaces=ns)
        if nodes and hasattr(nodes[0], "text") and nodes[0].text:
            return nodes[0].text.strip()
        return default

    title  = _one("//t:titleStmt/t:title")
    author = _one("//t:titleStmt/t:author")
    date   = _one("//t:publicationStmt/t:date")

    bodies = root.findall(f".//{{{TEI_NS}}}body")
    if not bodies:
        raise ValueError(f"No <body> found in TEI tree (text_id={text_id})")
    body_el = bodies[0]
    body_html = (body_el.text or "") + "".join(_el_to_html(c) for c in body_el)

    html = _HTML_TEMPLATE.format(
        text_id=text_id,
        title=title or "TEI Document",
        author=author,
        date=date,
        body=body_html,
    )

    if embed_css:
        html = html.replace(
            '<link rel="stylesheet" href="/static/css/text.css">',
            f"<style>{BUNDLED_CSS}</style>",
        )

    return html


def convert_file(path, text_id: int | str, *, embed_css: bool = False) -> str:
    """Parse *path* with lxml and call convert_tree()."""
    tree = etree.parse(str(path))
    return convert_tree(tree.getroot(), text_id, embed_css=embed_css)
