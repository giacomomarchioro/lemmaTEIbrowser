
import click
from pathlib import Path
from xml.etree import ElementTree as ET
from sqlalchemy import create_engine, text as sql_text
from sqlalchemy.orm import sessionmaker

from .models import Base, TextEntry, Word, Concept, Phraseme, PhrasemeWord


TEI_NS = {'tei': 'http://www.tei-c.org/ns/1.0'}


@click.command()
@click.argument('folder_path', type=click.Path(exists=True))
@click.option('--db-path', default='tei_database.db', help='Database file path')
def import_tei(folder_path, db_path):
    """Import .tei.xml files from FOLDER_PATH into database."""
    click.echo(f"Importing TEI files from: {folder_path}")
    click.echo(f"Database: {db_path}")
    
    # Create database
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Find TEI files
    folder = Path(folder_path)
    tei_files = list(folder.glob('*.tei.xml'))
    click.echo(f"Found {len(tei_files)} TEI XML files")
    
    # Process files
    batch_size = 10
    with click.progressbar(tei_files, label='Processing files') as bar:
        for i, file_path in enumerate(bar):
            try:
                parse_tei_file(file_path, session)
                
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
    
    click.echo(f"\nDatabase created successfully: {db_path}")
    
    session.close()


def parse_tei_file(file_path, session):
    """Parse a single TEI XML file."""
    tree = ET.parse(file_path)
    root = tree.getroot()
    
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
        return
    
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
    
    # Build word list from parent's text
    words = full_text.split()
    
    # Find the position of our specific word
    # We need to match by checking which word in the parent corresponds to our element
    try:
        # Get text before our element within parent
        text_before = []
        found_element = False
        
        for child in parent.iter():
            if child is element:
                found_element = True
                break
            if child.text:
                text_before.append(child.text)
            if child.tail:
                text_before.append(child.tail)
        
        # Also add parent's text if it comes before
        if parent.text:
            before_text = parent.text
            for child in parent:
                if child is element:
                    break
                if child is not element and hasattr(child, 'tail') and child.tail:
                    before_text += child.tail
            text_before.insert(0, before_text)
        
        # Count words before our element
        words_before = ' '.join(text_before).split()
        word_idx = len(words_before)
        
        # Extract context window
        start = max(0, word_idx - window)
        end = min(len(words), word_idx + window + 1)
        context = ' '.join(words[start:end])
        
        return context if context else full_text[:500]
        
    except Exception as e:
        # Fallback: return limited parent text
        return full_text[:500]

@click.command()
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=5000, help='Port to bind to')
@click.option('--debug/--no-debug', default=True, help='Enable debug mode')
def serve(host, port, debug):
    """Run the Flask development server."""
    from . import create_app
    app = create_app()
    click.echo(f"Starting server at http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    import_tei()
