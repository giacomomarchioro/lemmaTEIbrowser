
import click
from pathlib import Path
from xml.etree import ElementTree as ET
from lxml import etree
from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from .models import Base, TextEntry, Word, Concept, Phraseme, PhrasemeWord, get_session
from .tei_converter import convert_tree
from .xml_utils import ensure_word_ids
from .config import database_path, html_directory


TEI_NS = {'tei': 'http://www.tei-c.org/ns/1.0'}


@click.command()
@click.argument('folder_path', type=click.Path(exists=True, file_okay=False))
@click.option('--db-path', type=click.Path(dir_okay=False),
              help='Database file (overrides DATABASE_PATH; default: project tei_database.db)')
@click.option('--html-dir', type=click.Path(file_okay=False),
              help='Generated HTML directory (overrides TEXT_HTML_DIR; default: package static/texts)')
def import_tei(folder_path, db_path, html_dir):
    """Import .tei.xml files from FOLDER_PATH into database."""
    folder_path = Path(folder_path).expanduser().resolve()
    db_path = database_path(db_path)
    html_dir = html_directory(html_dir)
    if not db_path.parent.is_dir():
        raise click.ClickException(f'Database parent directory does not exist: {db_path.parent}')
    click.echo(f"Importing TEI files from: {folder_path}")
    click.echo(f"Database: {db_path}")
    click.echo(f"Full-text HTML: {html_dir}")
    
    # Create database
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Find TEI files
    folder = Path(folder_path)
    tei_files = sorted(folder.glob('*.tei.xml'))
    click.echo(f"Found {len(tei_files)} TEI XML files")
    
    # Process files
    failures = 0
    output_folder = Path(html_dir)
    output_folder.mkdir(parents=True, exist_ok=True)
    with click.progressbar(tei_files, label='Processing files') as bar:
        for file_path in bar:
            try:
                root = ET.parse(file_path).getroot()
                text_entry = parse_tei_file(file_path, session, root=root)
                # Render the same ID-enriched tree used for database import.
                html = convert_tree(etree.fromstring(ET.tostring(root)), text_entry.id)
                session.flush()
                output_file = output_folder / f'{text_entry.sourceFile}.tei.html'
                output_file.write_text(html, encoding='utf-8')
                session.commit()
                    
            except Exception as e:
                click.echo(f"\nError processing {file_path.name}: {e}", err=True)
                session.rollback()
                failures += 1
    
    session.commit()
    
    # Optimize database
    click.echo("\nOptimizing database...")
    with engine.connect() as conn:
        conn.execute(sql_text("PRAGMA journal_mode=WAL;"))
        conn.execute(sql_text("PRAGMA synchronous=NORMAL;"))
        conn.execute(sql_text("ANALYZE;"))
        conn.commit()
        
        # Print statistics (dentro lo stesso blocco with)
        stats = conn.execute(sql_text("""
            SELECT 
                (SELECT COUNT(*) FROM TEXTS) as texts,
                (SELECT COUNT(*) FROM WORDS) as words,
                (SELECT COUNT(*) FROM CONCEPTS) as concepts,
                (SELECT COUNT(*) FROM PHRASEMES) as phrasemes
        """)).fetchone()
        
        click.echo(f"\nDatabase Statistics:")
        click.echo(f"  Texts: {stats[0]}")
        click.echo(f"  Words: {stats[1]}")
        click.echo(f"  Concepts: {stats[2]}")
        click.echo(f"  Phrasemes: {stats[3]}")
    
    if not failures:
        click.echo(f"\nDatabase created successfully: {db_path}")
    
    session.close()
    engine.dispose()
    if failures:
        raise click.ClickException(f'{failures} file(s) failed to import; successful files were preserved.')


def parse_tei_file(file_path, session, *, root=None):
    """Parse a single TEI XML file."""
    if root is None:
        root = ET.parse(file_path).getroot()
    ensure_word_ids(root)
    
    # Extract metadata
    header = root.find('.//tei:teiHeader', TEI_NS)
    title_elem = header.find('.//tei:titleStmt/tei:title', TEI_NS)
    author_elem = header.find('.//tei:titleStmt/tei:author', TEI_NS)
    orig_date = header.find('.//tei:origin/tei:origDate', TEI_NS)
    
    title = title_elem.text if title_elem is not None else ""
    author = author_elem.text if author_elem is not None else ""
    not_before = orig_date.get('notBefore', '') if orig_date is not None else ''
    not_after = orig_date.get('notAfter', '') if orig_date is not None else ''
    
    # Extract sourceFile (filename without .tei.xml suffix)
    source_file = file_path.stem.replace('.tei', '')
    
    # Create text entry
    text_entry = TextEntry(
        author=author,
        title=title,
        notBefore=not_before,
        notAfter=not_after,
        sourceFile=source_file
    )
    session.add(text_entry)
    session.flush()
    
    # Find body
    body = root.find('.//tei:body', TEI_NS)
    if body is None:
        body = root.find('.//body')
    
    if body is None:
        raise ValueError('No <body> found in TEI file')
    
    # Process <w> elements
    w_elements = body.findall('.//tei:w', TEI_NS)
    if not w_elements:
        w_elements = body.findall('.//w')
    
    for w_elem in w_elements:
        xml_id = w_elem.get('{http://www.w3.org/XML/1998/namespace}id') or w_elem.get('xml:id')
        occurrence = ''.join(w_elem.itertext()).strip()
        lemma = w_elem.get('lemma', '')
        ana_url = w_elem.get('ana', '')
        
        # Get or create concept
        concept = None
        if ana_url:
            concept = session.query(Concept).filter_by(URLconcept=ana_url).first()
            if not concept:
                concept = Concept(URLconcept=ana_url)
                session.add(concept)
                session.flush()
        
        # Build context
        context = get_surrounding_text(w_elem, root, window=150)
        
        # Create word entry
        word_entry = Word(
            id_text=text_entry.id,
            xml_id_word=xml_id,
            occurrence=occurrence,
            lemma=lemma,
            id_concept=concept.id_concept if concept else None,
            context=context
        )
        session.add(word_entry)
    
    # Process <span> elements
    span_elements = body.findall('.//tei:span[@type="baseForm"]', TEI_NS)
    if not span_elements:
        span_elements = body.findall('.//span[@type="baseForm"]')
    
    for span_elem in span_elements:
        target = span_elem.get('target', '')
        normalized = span_elem.get('n', '')
        concept_url = span_elem.get('ana', '')
        
        xml_ids = [t.lstrip('#') for t in target.split()]
        
        # Get or create concept
        concept = None
        if concept_url:
            concept = session.query(Concept).filter_by(URLconcept=concept_url).first()
            if not concept:
                concept = Concept(URLconcept=concept_url)
                session.add(concept)
                session.flush()
        
        # Create phraseme entry
        phraseme = Phraseme(
            id_text=text_entry.id,
            normalized_form=normalized,
            id_concept=concept.id_concept if concept else None
        )
        session.add(phraseme)
        session.flush()
        
        # Link words
        for position, xml_id in enumerate(xml_ids, start=1):
            word = session.query(Word).filter_by(
                xml_id_word=xml_id,
                id_text=text_entry.id
            ).first()
            
            if word:
                phraseme_word = PhrasemeWord(
                    id_phraseme=phraseme.id,
                    id_word_entry=word.id_word_entry,
                    position=position
                )
                session.add(phraseme_word)

    return text_entry


def get_surrounding_text(element, root, window=25):
    """Extract context around a <w> element."""
    # Find parent by iterating through all elements
    parent = None
    for p in root.iter():
        # Check if element is a direct child
        for child in p:
            if child is element:
                parent = p
                break
        if parent is not None:
            break
    
    if parent is None:
        return ""
    
    # Get all text from parent, preserving order
    full_text = ''.join(parent.itertext())
    word_text = ''.join(element.itertext()).strip()
    
    if not word_text:
        return full_text[:500]
    
    before = parent.text or ''
    after = element.tail or ''
    found = False
    for child in parent:
        if child is element:
            found = True
        elif found:
            after += ''.join(child.itertext()) + (child.tail or '')
        else:
            before += ''.join(child.itertext()) + (child.tail or '')

    # Slice around this element, not the first identical surface form.
    left = before.split()[-window:] if window > 0 else []
    right = after.split()[:window] if window > 0 else []
    return ' '.join(left + [word_text] + right)

@click.command()
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=5000, help='Port to bind to')
@click.option('--debug/--no-debug', default=True, help='Enable debug mode')
@click.option('--db-path', type=click.Path(dir_okay=False),
              help='Existing database (overrides DATABASE_PATH; default: project tei_database.db)')
@click.option('--html-dir', type=click.Path(file_okay=False),
              help='Full-text HTML directory (overrides TEXT_HTML_DIR; default: package static/texts)')
def serve(host, port, debug, db_path, html_dir):
    """Run the Flask development server."""
    from . import create_app
    db_path = database_path(db_path)
    html_dir = html_directory(html_dir)
    click.echo(f"Database: {db_path}")
    click.echo(f"Full-text HTML: {html_dir}")
    if not db_path.is_file():
        raise click.ClickException(
            f'Database file does not exist: {db_path}. '
            'Use --db-path to select an existing database, or run lemma-import first.'
        )
    try:
        app = create_app(config_overrides={
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'DATABASE_PATH': str(db_path),
            'TEXT_HTML_DIR': str(html_dir),
        })
        with get_session() as session:
            text_count = session.query(TextEntry).count()
            word_count = session.query(Word).count()
    except SQLAlchemyError as error:
        raise click.ClickException(
            f'Unable to open database {db_path}. Check file and parent directory permissions. {error}'
        ) from error
    click.echo(f"Templates: {Path(app.root_path) / 'templates'}")
    click.echo(f"Static assets: {app.static_folder}")
    click.echo(f"Database contents: {text_count} texts, {word_count} words")
    if word_count == 0:
        click.echo('Warning: this database contains no words. Select the imported database with --db-path.', err=True)
    if not html_dir.is_dir():
        click.echo('Warning: full-text HTML directory is missing; full-text links will return 404.', err=True)
    click.echo(f"Starting server at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    import_tei()
