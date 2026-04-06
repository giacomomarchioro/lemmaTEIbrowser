
"""SQLAlchemy database models for TEI texts."""

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
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()
Session = None


def init_db(app):
    """Initialize database with Flask app."""
    global Session
    engine = create_engine(
        app.config['SQLALCHEMY_DATABASE_URI'],
        echo=app.config['DEBUG'],
        connect_args={'check_same_thread': False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)


def get_session():
    """Get a new database session."""
    if Session is None:
        raise RuntimeError("Database not initialized. Call init_db first.")
    return Session()


class TextEntry(Base):
    """TEI text metadata."""
    __tablename__ = 'TEXTS'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    author = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False, index=True)
    notBefore = Column(String(50))
    notAfter = Column(String(50))
    
    words = relationship("Word", back_populates="text", cascade="all, delete-orphan")
    phrasemes = relationship("Phraseme", back_populates="text", cascade="all, delete-orphan")
    
    __table_args__ = (Index('idx_text_author_title', 'author', 'title'),)


class Concept(Base):
    """Concept from TEI ana attribute."""
    __tablename__ = 'CONCEPTS'
    
    id_concept = Column(Integer, primary_key=True, autoincrement=True)
    URLconcept = Column(String(500), unique=True, nullable=False, index=True)
    
    words = relationship("Word", back_populates="concept")
    phrasemes = relationship("Phraseme", back_populates="concept")


class Word(Base):
    """Individual word occurrence from TEI <w> element."""
    __tablename__ = 'WORDS'
    
    id_word_entry = Column(Integer, primary_key=True, autoincrement=True)
    id_text = Column(Integer, ForeignKey('TEXTS.id', ondelete='CASCADE'), nullable=False, index=True)
    xml_id_word = Column(String(100), nullable=False)
    occurrence = Column(String(255), nullable=False, index=True)
    lemma = Column(String(255), index=True)
    id_concept = Column(Integer, ForeignKey('CONCEPTS.id_concept', ondelete='SET NULL'), index=True)
    context = Column(Text)
    
    text = relationship("TextEntry", back_populates="words")
    concept = relationship("Concept", back_populates="words")
    phraseme_associations = relationship("PhrasemeWord", back_populates="word")
    
    __table_args__ = (
        UniqueConstraint('id_text', 'xml_id_word', name='uq_text_xmlid'),
        Index('idx_word_lemma_text', 'lemma', 'id_text'),
        Index('idx_word_occurrence', 'occurrence'),
    )


class Phraseme(Base):
    """Multi-word expression from TEI <span type="baseForm">."""
    __tablename__ = 'PHRASEMES'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_text = Column(Integer, ForeignKey('TEXTS.id', ondelete='CASCADE'), nullable=False, index=True)
    normalized_form = Column(String(500), nullable=False, index=True)
    id_concept = Column(Integer, ForeignKey('CONCEPTS.id_concept', ondelete='SET NULL'), index=True)
    
    text = relationship("TextEntry", back_populates="phrasemes")
    concept = relationship("Concept", back_populates="phrasemes")
    words = relationship("PhrasemeWord", back_populates="phraseme", cascade="all, delete-orphan")


class PhrasemeWord(Base):
    """Junction table linking phrasemes to their component words."""
    __tablename__ = 'PHRASEME_WORDS'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    id_phraseme = Column(Integer, ForeignKey('PHRASEMES.id', ondelete='CASCADE'), nullable=False, index=True)
    id_word_entry = Column(Integer, ForeignKey('WORDS.id_word_entry', ondelete='CASCADE'), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    
    phraseme = relationship("Phraseme", back_populates="words")
    word = relationship("Word", back_populates="phraseme_associations")
    
    __table_args__ = (
        UniqueConstraint('id_phraseme', 'position', name='uq_phraseme_position'),
        Index('idx_phraseme_word', 'id_phraseme', 'id_word_entry'),
    )