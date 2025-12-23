import os
from pathlib import Path
from xml.etree import ElementTree as ET
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
)
# from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy import text


Base = declarative_base()


# Define database models
class TextEntry(Base):
    __tablename__ = "TEXTS"

    id = Column(Integer, primary_key=True, autoincrement=True)
    author = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False, index=True)
    notBefore = Column(String(50))
    notAfter = Column(String(50))

    words = relationship("Word", back_populates="text", cascade="all, delete-orphan")
    phrasemes = relationship(
        "Phraseme", back_populates="text", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_text_author_title", "author", "title"),)


class Concept(Base):
    __tablename__ = "CONCEPTS"

    id_concept = Column(Integer, primary_key=True, autoincrement=True)
    URLconcept = Column(String(500), unique=True, nullable=False, index=True)

    words = relationship("Word", back_populates="concept")


class Word(Base):
    __tablename__ = "WORDS"

    id_word_entry = Column(Integer, primary_key=True, autoincrement=True)
    id_text = Column(
        Integer, ForeignKey("TEXTS.id", ondelete="CASCADE"), nullable=False, index=True
    )
    xml_id_word = Column(String(100), nullable=False)
    occurrence = Column(String(255), nullable=False, index=True)
    lemma = Column(String(255), index=True)
    id_concept = Column(
        Integer, ForeignKey("CONCEPTS.id_concept", ondelete="SET NULL"), index=True
    )
    context = Column(Text)

    text = relationship("TextEntry", back_populates="words")
    concept = relationship("Concept", back_populates="words")
    phraseme_associations = relationship("PhrasemeWord", back_populates="word")

    __table_args__ = (
        UniqueConstraint("id_text", "xml_id_word", name="uq_text_xmlid"),
        Index("idx_word_lemma_text", "lemma", "id_text"),
        Index("idx_word_occurrence", "occurrence"),
    )


class Phraseme(Base):
    __tablename__ = "PHRASEMES"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_text = Column(
        Integer, ForeignKey("TEXTS.id", ondelete="CASCADE"), nullable=False, index=True
    )
    normalized_form = Column(String(500), nullable=False, index=True)
    concept_url = Column(String(500), index=True)

    text = relationship("TextEntry", back_populates="phrasemes")
    words = relationship(
        "PhrasemeWord", back_populates="phraseme", cascade="all, delete-orphan"
    )


class PhrasemeWord(Base):
    __tablename__ = "PHRASEME_WORDS"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_phraseme = Column(
        Integer,
        ForeignKey("PHRASEMES.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_word_entry = Column(
        Integer,
        ForeignKey("WORDS.id_word_entry", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position = Column(Integer, nullable=False)

    phraseme = relationship("Phraseme", back_populates="words")
    word = relationship("Word", back_populates="phraseme_associations")

    __table_args__ = (
        UniqueConstraint("id_phraseme", "position", name="uq_phraseme_position"),
        Index("idx_phraseme_word", "id_phraseme", "id_word_entry"),
    )


# TEI namespace
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def get_text_content(element):
    """Extract all text content from an element and its children."""
    if element is None:
        return ""
    return "".join(element.itertext())


def extract_context(all_words, current_idx, window=25):
    """Extract context: 25 words before and after the current word."""
    start = max(0, current_idx - window)
    end = min(len(all_words), current_idx + window + 1)
    context_words = all_words[start:end]
    return " ".join(context_words)


def parse_tei_file(file_path, session):
    """Parse a single TEI XML file and populate the database."""
    tree = ET.parse(file_path)
    root = tree.getroot()

    # Extract metadata from teiHeader
    header = root.find(".//tei:teiHeader", TEI_NS)

    # Extract title
    title_elem = header.find(".//tei:titleStmt/tei:title", TEI_NS)
    title = title_elem.text if title_elem is not None else ""

    # Extract author
    author_elem = header.find(".//tei:titleStmt/tei:author", TEI_NS)
    author = author_elem.text if author_elem is not None else ""

    # Extract date range
    orig_date = header.find(".//tei:origin/tei:origDate", TEI_NS)
    not_before = orig_date.get("notBefore", "") if orig_date is not None else ""
    not_after = orig_date.get("notAfter", "") if orig_date is not None else ""

    # Create text entry
    text_entry = TextEntry(
        author=author, title=title, notBefore=not_before, notAfter=not_after
    )
    session.add(text_entry)
    session.flush()  # Get the ID without committing

    # Extract all text content for context building
    body = root.find(".//tei:body", TEI_NS)
    if body is None:
        body = root.find(".//body")  # Try without namespace

    if body is None:
        print(f"Warning: No body found in {file_path}")
        return

    # Get all words as text for context
    all_text_words = []
    for elem in body.iter():
        if elem.text:
            all_text_words.extend(elem.text.split())
        if elem.tail:
            all_text_words.extend(elem.tail.split())

    # Process <w> elements
    w_elements = body.findall(".//tei:w", TEI_NS)
    if not w_elements:
        w_elements = body.findall(".//w")  # Try without namespace

    word_position = 0
    for w_elem in w_elements:
        xml_id = w_elem.get("{http://www.w3.org/XML/1998/namespace}id") or w_elem.get(
            "xml:id"
        )
        occurrence = get_text_content(w_elem).strip()
        lemma = w_elem.get("lemma", "")
        ana_url = w_elem.get("ana", "")

        # Get or create concept
        concept = None
        if ana_url:
            concept = session.query(Concept).filter_by(URLconcept=ana_url).first()
            if not concept:
                concept = Concept(URLconcept=ana_url)
                session.add(concept)
                session.flush()

        # Build context
        context = extract_context(all_text_words, word_position)
        word_position += len(occurrence.split())

        # Create word entry
        word_entry = Word(
            id_text=text_entry.id,
            xml_id_word=xml_id,
            occurrence=occurrence,
            lemma=lemma,
            id_concept=concept.id_concept if concept else None,
            context=context,
        )
        session.add(word_entry)
    print(len(w_elements))
    # Process <span> elements for phrasemes
    span_elements = body.findall('.//tei:span[@type="baseForm"]', TEI_NS)
    if not span_elements:
        span_elements = body.findall('.//span[@type="baseForm"]')

    for span_elem in span_elements:
        target = span_elem.get("target", "")
        normalized = span_elem.get("n", "")
        concept_url = span_elem.get("ana", "")

        # Extract xml:id values from target (remove # prefix)
        xml_ids = [t.lstrip("#") for t in target.split()]

        # Create phraseme entry
        phraseme = Phraseme(
            id_text=text_entry.id, normalized_form=normalized, concept_url=concept_url
        )
        session.add(phraseme)
        session.flush()  # Get the phraseme ID

        # Link words to phraseme through junction table
        for position, xml_id in enumerate(xml_ids, start=1):
            # Find the word with matching xml_id_word and id_text
            word = (
                session.query(Word)
                .filter_by(xml_id_word=xml_id, id_text=text_entry.id)
                .first()
            )

            if word:
                phraseme_word = PhrasemeWord(
                    id_phraseme=phraseme.id,
                    id_word_entry=word.id_word_entry,
                    position=position,
                )
                session.add(phraseme_word)
            else:
                print(f"Warning: Word with xml:id '{xml_id}' not found for phraseme")


def process_folder(folder_path, db_path="tei_database.db"):
    """Process all .tei.xml files in a folder and create the database."""
    # Create database engine with optimizations
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,  # Set to True for SQL debugging
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # Find all .tei.xml files
    folder = Path(folder_path)
    tei_files = list(folder.glob("*.tei.xml"))

    print(f"Found {len(tei_files)} TEI XML files")

    # Process files in batches for better performance
    batch_size = 10
    for i, file_path in enumerate(tei_files):
        print(f"Processing: {file_path.name} ({i + 1}/{len(tei_files)})")
        try:
            parse_tei_file(file_path, session)

            # Commit in batches
            if (i + 1) % batch_size == 0:
                session.commit()
                print(f"  Committed batch of {batch_size} files")

        except Exception as e:
            print(f"Error processing {file_path.name}: {e}")
            session.rollback()
            continue

    # Commit remaining changes
    session.commit()

    # Create additional indexes after bulk insert (more efficient)
    print("\nOptimizing database...")
    with engine.connect() as conn:
        conn.execute(text(
            "PRAGMA journal_mode=WAL;")
        )  # Write-Ahead Logging for better concurrency
        conn.execute(text("PRAGMA synchronous=NORMAL;"))  # Faster writes
        conn.execute(text("ANALYZE;"))  # Update statistics for query optimizer

    session.close()

    print(f"\nDatabase created successfully: {db_path}")

    # Print statistics
    with engine.connect() as conn:
        stats = conn.execute(text("""
            SELECT 
                (SELECT COUNT(*) FROM TEXTS) as texts,
                (SELECT COUNT(*) FROM WORDS) as words,
                (SELECT COUNT(*) FROM CONCEPTS) as concepts,
                (SELECT COUNT(*) FROM PHRASEMES) as phrasemes
        """)).fetchone()
        print(f"\nDatabase Statistics:")
        print(f"  Texts: {stats[0]}")
        print(f"  Words: {stats[1]}")
        print(f"  Concepts: {stats[2]}")
        print(f"  Phrasemes: {stats[3]}")


process_folder("tei-xml-ids")