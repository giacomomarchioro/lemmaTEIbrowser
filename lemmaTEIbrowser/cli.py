
"""Command-line interface for importing TEI files and running the server."""

import click
from pathlib import Path
from xml.etree import ElementTree as ET
from sqlalchemy import create_engine, engine, text as sql_text
from sqlalchemy.orm import sessionmaker
import uuid

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

    with engine.connect() as conn:
        stats = conn.execute(sql_text("""
            SELECT 
                (SELECT COUNT(*) FROM TEXTS),
                (SELECT COUNT(*) FROM WORDS),
                (SELECT COUNT(*) FROM CONCEPTS),
                (SELECT COUNT(*) FROM PHRASEMES)
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
    # --- AGGIUNTA: Crea mappa dei genitori per sopperire alla mancanza di getparent() ---
    parent_map = {c: p for p in root.iter() for c in p}
    # Extract metadata
    header = root.find('.//tei:teiHeader', TEI_NS)
    title_elem = header.find('.//tei:titleStmt/tei:title', TEI_NS)
    author_elem = header.find('.//tei:titleStmt/tei:author', TEI_NS)
    orig_date = header.find('.//tei:origin/tei:origDate', TEI_NS)
    
    title = title_elem.text if title_elem is not None else ""
    author = author_elem.text if author_elem is not None else ""
    not_before = orig_date.get('notBefore', '') if orig_date is not None else ''
    not_after = orig_date.get('notAfter', '') if orig_date is not None else ''
    
    # Create text entry
    text_entry = TextEntry(
        author=author,
        title=title,
        notBefore=not_before,
        notAfter=not_after
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
    w_elements = body.findall('.//tei:w', TEI_NS) or body.findall('.//w')
    
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
        # --- MODIFICA: Trova il nodo di contesto (p, s, o div) ---
        context_node = w_elem
        while context_node in parent_map:
            parent = parent_map[context_node]
            # Controlla il tag ignorando il namespace
            tag_name = parent.tag.split('}')[-1] 
            if tag_name in ['p', 's', 'div', 'ab']:
                context_node = parent
                break
            context_node = parent
        
        # Se non trova un contenitore specifico, usa il body come fallback
        if context_node == w_elem:
            context_node = body

        # --- CHIAMATA: Usa la nuova funzione con il contesto trovato ---
        context = get_surrounding_text(w_elem, context_node, window=30)
        
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

def get_surrounding_text(element, context_node, window=100):
    """Estrae esattamente 'window' caratteri prima e dopo il nodo target."""
    if element is None or context_node is None:
        return ""

    marker_id = f"MARK_{uuid.uuid4().hex[:8]}"
    start_m, end_m = f"[[{marker_id}_S]]", f"[[{marker_id}_E]]"
    original_text = element.text or ""
    
    try:
        element.text = start_m + original_text + end_m
        full_text = "".join(context_node.itertext())
        
        s_idx = full_text.find(start_m)
        e_idx = full_text.find(end_m)
        
        if s_idx == -1: return original_text
        # 1. Estrai i 30 caratteri grezzi (come prima)
        prefix_raw = full_text[max(0, s_idx - window) : s_idx]
        suffix_raw = full_text[e_idx + len(end_m) : e_idx + len(end_m) + window]

        # 2. Pulizia Prefisso: 
        # Cerchiamo il primo spazio da sinistra. Tutto quello che c'è prima 
        # dello spazio è una parola troncata, quindi lo scartiamo.
        first_space_pre = prefix_raw.find(" ")
        if first_space_pre != -1 and s_idx > window:
            prefix = "..." + prefix_raw[first_space_pre:]
        else:
            prefix = prefix_raw

        # 3. Pulizia Suffisso:
        # Cerchiamo l'ultimo spazio da destra. Tutto quello che c'è dopo 
        # l'ultimo spazio è troncato, quindi lo scartiamo.
        last_space_suf = suffix_raw.rfind(" ")
        if last_space_suf != -1 and (len(full_text) - (e_idx + len(end_m))) > window:
            suffix = suffix_raw[:last_space_suf] + "..."
        else:
            suffix = suffix_raw

        # 4. Unione Finale
        # Non aggiungiamo spazi artificiali tra prefix, original_text e suffix
        # perché lo spazio corretto è già contenuto nelle stringhe estratte dal TEI
        context = f"{prefix}{original_text}{suffix}"

        return context
    finally:
        element.text = original_text


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