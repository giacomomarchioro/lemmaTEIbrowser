#!/usr/bin/env python3
"""
tei2html.py  –  Convert a TEI XML file to a self-contained HTML page.

Usage:
    python tei2html.py input.xml [output.html]

If output.html is omitted the result is written to stdout.

Word elements (<w xml:id="...">) become:
    <span class="w" id="WORD_ID">...</span>

Linking to a specific word:
    yourpage.html?w=l_w0001
    → the page scrolls to that span and highlights it.
"""

import sys
import re
from lxml import etree

TEI_NS = "http://www.tei-c.org/ns/1.0"

def tag(el):
    """Return the local tag name, stripping any namespace."""
    return el.tag.split("}")[-1] if "}" in el.tag else el.tag


def el_to_html(el) -> str:
    """Recursively convert a TEI element to an HTML string."""
    t = tag(el)

    # --- <w> → <span class="w" id="..."> ---
    if t == "w":
        wid = el.get("{http://www.w3.org/XML/1998/namespace}id") or el.get("xml:id", "")
        id_attr = f' id="{wid}"' if wid else ""
        inner = (el.text or "") + "".join(el_to_html(c) for c in el)
        tail  = el.tail or ""
        return f'<span class="w"{id_attr}>{inner}</span>{tail}'

    # --- <head> → <h2> ---
    if t == "head":
        inner = (el.text or "") + "".join(el_to_html(c) for c in el)
        tail  = el.tail or ""
        return f"<h2>{inner}</h2>{tail}"

    # --- <p> → <p> ---
    if t == "p":
        inner = (el.text or "") + "".join(el_to_html(c) for c in el)
        tail  = el.tail or ""
        return f"<p>{inner}</p>{tail}"

    # --- <div> → <section> ---
    if t == "div":
        dtype = el.get("type", "")
        inner = (el.text or "") + "".join(el_to_html(c) for c in el)
        tail  = el.tail or ""
        return f'<section class="div-{dtype}">{inner}</section>{tail}'

    # --- anything else: recurse, keep text ---
    inner = (el.text or "") + "".join(el_to_html(c) for c in el)
    tail  = el.tail or ""
    return inner + tail


def extract_meta(root) -> dict:
    """Pull basic metadata from teiHeader for the HTML <head>."""
    ns = {"t": TEI_NS}
    def one(xpath, default=""):
        nodes = root.xpath(xpath, namespaces=ns)
        return nodes[0].text.strip() if nodes and nodes[0].text else default

    return {
        "title":  one("//t:titleStmt/t:title"),
        "author": one("//t:titleStmt/t:author"),
        "date":   one("//t:publicationStmt/t:date"),
    }


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{
      max-width: 780px;
      margin: 2rem auto;
      padding: 0 1.5rem;
      font-family: Georgia, serif;
      line-height: 1.75;
      color: #1a1a1a;
    }}
    header {{
      border-bottom: 1px solid #ccc;
      margin-bottom: 2rem;
      padding-bottom: 1rem;
    }}
    header p {{ margin: 0.2rem 0; color: #555; font-style: italic; }}
    section.div-chapter {{ margin-bottom: 2.5rem; }}
    h2 {{
      font-size: 1rem;
      text-transform: uppercase;
      letter-spacing: .08em;
      margin-bottom: .25rem;
    }}
    span.w {{
      /* no visible styling by default */
      cursor: pointer;
    }}
    span.w:target,
    span.w.highlight {{
      background: #ffe08a;
      border-radius: 2px;
      outline: 2px solid #f0b429;
    }}
  </style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <p>{author}</p>
  <p>{date}</p>
</header>
<main>
{body}
</main>
<script>
  // Highlight and scroll to a word by query parameter ?w=WORD_ID
  (function () {{
    const params = new URLSearchParams(window.location.search);
    const wid = params.get("w");
    if (!wid) return;
    const target = document.getElementById(wid);
    if (!target) return;
    target.classList.add("highlight");
    target.scrollIntoView({{ behavior: "smooth", block: "center" }});
  }})();
</script>
</body>
</html>
"""


def convert(xml_path: str) -> str:
    tree = etree.parse(xml_path)
    root = tree.getroot()
    meta = extract_meta(root)

    # Find <body>
    bodies = root.findall(f".//{{{TEI_NS}}}body")
    if not bodies:
        raise ValueError("<body> element not found in TEI file.")
    body_el = bodies[0]

    body_html = (body_el.text or "") + "".join(el_to_html(c) for c in body_el)

    return HTML_TEMPLATE.format(
        title=meta["title"] or "TEI Document",
        author=meta["author"],
        date=meta["date"],
        body=body_html,
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    xml_path = sys.argv[1]
    html = convert(xml_path)

    if len(sys.argv) >= 3:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Written to {sys.argv[2]}")
    else:
        print(html)
