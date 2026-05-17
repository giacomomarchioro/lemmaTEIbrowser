"""Command-line interface for importing TEI files and running the server."""

import re
import click
from pathlib import Path
from xml.etree import ElementTree as ET
from lxml import etree as lxml_etree          # used only for HTML generation
from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.orm import sessionmaker
import uuid

from .models import Base, TextEntry, Word, Concept, Phraseme, PhrasemeWord
from .tei_converter import convert_tree as tei_convert_tree   # <-- new


TEI_NS     = {'tei': 'http://www.tei-c.org/ns/1.0'}
TEI_NS_URI = 'http://www.tei-c.org/ns/1.0'

# Where pre-generated HTML files land, relative to this package's directory.
# Adjust if your Flask app root differs from the package root.
_PKG_DIR    = Path(__file__).parent
TEXTS_DIR   = _PKG_DIR / 'static' / 'texts'


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def generate_html(file_path: Path, text_entry: TextEntry, output_dir: Path) -> Path:
    """Convert *file_path* to HTML and write it to *output_dir*.

    File name pattern: ``{text_entry.id}_{slug}.html``

    Returns the written Path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    out_name = f"{file_path.stem}.html"
    out_path = output_dir / out_name

    # Re-parse with lxml (stdlib ET is already used for the DB side; keep them
    # independent so neither parse mutates the other's tree).
    root = lxml_etree.parse(str(file_path)).getroot()
    html = tei_convert_tree(root, text_entry.id)

    out_path.write_text(html, encoding='utf-8')
    return out_path


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.command()
@click.argument('folder_path', type=click.Path(exists=True))
@click.option('--db-path',    default='tei_database.db', help='Database file path')
@click.option('--html-dir',   default=None,
              help='Directory for generated HTML files '
                   f'(default: {TEXTS_DIR})')
@click.option('--no-html',    is_flag=True, default=False,
              help='Skip HTML generation (DB import only)')
def import_tei(folder_path, db_path, html_dir, no_html):
    """Import .tei.xml files from FOLDER_PATH into database.

    For each file a static HTML rendering is also written to
    static/texts/ (or --html-dir) so Flask can serve it directly at
    /static/texts/<id>_<slug>.html?w=WORD_ID
    """
    click.echo(f"Importing TEI files from: {folder_path}")
    click.echo(f"Database: {db_path}")

    output_dir = Path(html_dir) if html_dir else TEXTS_DIR
    if not no_html:
        click.echo(f"HTML output:  {output_dir}")

    # Create database
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Find TEI files
    folder    = Path(folder_path)
    tei_files = list(folder.glob('*.tei.xml'))
    click.echo(f"Found {len(tei_files)} TEI XML files")

    html_ok    = 0
    html_fail  = 0
    batch_size = 10

    with click.progressbar(tei_files, label='Processing files') as bar:
        for i, file_path in enumerate(bar):
            try:
                text_entry = parse_tei_file(file_path, session)

                # Generate HTML right after the DB row exists (id is available
                # after flush() inside parse_tei_file).
                if not no_html and text_entry is not None:
                    try:
                        out = generate_html(file_path, text_entry, output_dir)
                        html_ok += 1
                        click.echo(f"\n  HTML → {out.name}", err=False)
                    except Exception as html_err:
                        html_fail += 1
                        click.echo(
                            f"\n  HTML generation failed for {file_path.name}: {html_err}",
                            err=True,
                        )

                if (i + 1) % batch_size == 0:
                    session.commit()

            except Exception as e:
                click.echo(f"\nError processing {file_path.name}: {e}", err=True)
                session.rollback()

    session.commit()

    # Optimize database
    click.echo("\nOptimizing database...")
    with engine.connect() as conn:
        conn.execute(sql_text("PRAGMA journal_mode=WAL;"))
        conn.execute(sql_text("PRAGMA synchronous=NORMAL;"))
        conn.execute(sql_text("ANALYZE;"))
        conn.commit()

    with engine.connect() as conn:
        stats = conn.execute(sql_text("""
            SELECT
                (SELECT COUNT(*) FROM TEXTS),
                (SELECT COUNT(*) FROM WORDS),
                (SELECT COUNT(*) FROM CONCEPTS),
                (SELECT COUNT(*) FROM PHRASEMES)
        """)).fetchone()

    click.echo(f"\nDatabase Statistics:")
    click.echo(f"  Texts:    {stats[0]}")
    click.echo(f"  Words:    {stats[1]}")
    click.echo(f"  Concepts: {stats[2]}")
    click.echo(f"  Phrasemes:{stats[3]}")
    if not no_html:
        click.echo(f"  HTML OK:  {html_ok}")
        if html_fail:
            click.echo(f"  HTML ERR: {html_fail}  (see stderr above)")
    click.echo(f"\nDatabase created successfully: {db_path}")

    session.close()


# ---------------------------------------------------------------------------
# TEI parser (DB side — unchanged logic, now returns text_entry)
# ---------------------------------------------------------------------------

def parse_tei_file(file_path: Path, session) -> TextEntry | None:
    """Parse a single TEI XML file into the DB. Returns the TextEntry."""
    tree = ET.parse(file_path)
    root = tree.getroot()

    # Parent map (stdlib ET has no getparent())
    parent_map = {c: p for p in root.iter() for c in p}

    # Metadata
    header     = root.find('.//tei:teiHeader', TEI_NS)
    title_elem = header.find('.//tei:titleStmt/tei:title',  TEI_NS)
    author_elem= header.find('.//tei:titleStmt/tei:author', TEI_NS)
    orig_date  = header.find('.//tei:origin/tei:origDate',  TEI_NS)

    title      = title_elem.text  if title_elem   is not None else ""
    author     = author_elem.text if author_elem  is not None else ""
    not_before = orig_date.get('notBefore', '') if orig_date is not None else ''
    not_after  = orig_date.get('notAfter',  '') if orig_date is not None else ''

    text_entry = TextEntry(
        author=author, title=title,
        notBefore=not_before, notAfter=not_after,sourceFile=file_path.stem
    )
    session.add(text_entry)
    session.flush()   # populate text_entry.id

    # Body
    body = root.find('.//tei:body', TEI_NS) or root.find('.//body')
    if body is None:
        return text_entry   # still return so caller can try HTML generation

    # --- <w> elements ---
    w_elements = body.findall('.//tei:w', TEI_NS) or body.findall('.//w')

    for w_elem in w_elements:
        xml_id     = (w_elem.get('{http://www.w3.org/XML/1998/namespace}id')
                      or w_elem.get('xml:id'))
        occurrence = ''.join(w_elem.itertext()).strip()
        lemma      = w_elem.get('lemma', '')
        ana_url    = w_elem.get('ana',   '')

        concept = None
        if ana_url:
            concept = session.query(Concept).filter_by(URLconcept=ana_url).first()
            if not concept:
                concept = Concept(URLconcept=ana_url)
                session.add(concept)
                session.flush()

        # Context node: walk up to p / s / div / ab
        context_node = w_elem
        while context_node in parent_map:
            parent   = parent_map[context_node]
            tag_name = parent.tag.split('}')[-1]
            if tag_name in ('p', 's', 'div', 'ab'):
                context_node = parent
                break
            context_node = parent
        if context_node is w_elem:
            context_node = body

        context = get_surrounding_text(w_elem, context_node)

        word_entry = Word(
            id_text      = text_entry.id,
            xml_id_word  = xml_id,
            occurrence   = occurrence,
            lemma        = lemma,
            id_concept   = concept.id_concept if concept else None,
            context      = context,
        )
        session.add(word_entry)

    # --- <span type="baseForm"> elements ---
    span_elements = (body.findall('.//tei:span[@type="baseForm"]', TEI_NS)
                     or body.findall('.//span[@type="baseForm"]'))

    for span_elem in span_elements:
        target      = span_elem.get('target',  '')
        normalized  = span_elem.get('n',       '')
        concept_url = span_elem.get('ana',     '')
        xml_ids     = [t.lstrip('#') for t in target.split()]

        concept = None
        if concept_url:
            concept = session.query(Concept).filter_by(URLconcept=concept_url).first()
            if not concept:
                concept = Concept(URLconcept=concept_url)
                session.add(concept)
                session.flush()

        phraseme = Phraseme(
            id_text         = text_entry.id,
            normalized_form = normalized,
            id_concept      = concept.id_concept if concept else None,
        )
        session.add(phraseme)
        session.flush()

        for position, xml_id in enumerate(xml_ids, start=1):
            word = session.query(Word).filter_by(
                xml_id_word=xml_id, id_text=text_entry.id).first()
            if word:
                session.add(PhrasemeWord(
                    id_phraseme   = phraseme.id,
                    id_word_entry = word.id_word_entry,
                    position      = position,
                ))

    return text_entry


def get_surrounding_text(element, context_node, window=100):
    """Extract up to *window* chars of context around *element*."""
    if element is None or context_node is None:
        return ""

    marker_id   = f"MARK_{uuid.uuid4().hex[:8]}"
    start_m     = f"[[{marker_id}_S]]"
    end_m       = f"[[{marker_id}_E]]"
    original    = element.text or ""

    try:
        element.text = start_m + original + end_m
        full_text    = "".join(context_node.itertext())

        s_idx = full_text.find(start_m)
        e_idx = full_text.find(end_m)
        if s_idx == -1:
            return original

        prefix_raw = full_text[max(0, s_idx - window): s_idx]
        suffix_raw = full_text[e_idx + len(end_m): e_idx + len(end_m) + window]

        first_space = prefix_raw.find(" ")
        if first_space != -1 and s_idx > window:
            prefix = "..." + prefix_raw[first_space:]
        else:
            prefix = prefix_raw

        last_space = suffix_raw.rfind(" ")
        if last_space != -1 and (len(full_text) - (e_idx + len(end_m))) > window:
            suffix = suffix_raw[:last_space] + "..."
        else:
            suffix = suffix_raw

        return f"{prefix}{original}{suffix}"
    finally:
        element.text = original


# ---------------------------------------------------------------------------

@click.command()
@click.option('--host',  default='127.0.0.1')
@click.option('--port',  default=5000)
@click.option('--debug/--no-debug', default=True)
def serve(host, port, debug):
    """Run the Flask development server."""
    from . import create_app
    app = create_app()
    click.echo(f"Starting server at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    import_tei()
