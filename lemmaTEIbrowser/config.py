
"""Application configuration."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = BASE_DIR / 'tei_database.db'
DEFAULT_HTML_DIR = BASE_DIR / 'lemmaTEIbrowser' / 'static' / 'texts'


def database_path(value=None):
    """Explicit option, environment, then the shared project default."""
    return Path(value or os.environ.get('DATABASE_PATH') or DEFAULT_DATABASE_PATH).expanduser().resolve()


def html_directory(value=None):
    return Path(value or os.environ.get('TEXT_HTML_DIR') or DEFAULT_HTML_DIR).expanduser().resolve()


class Config:
    """Base configuration."""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database
    BASE_DIR = BASE_DIR
    DATABASE_PATH = str(database_path())
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DATABASE_PATH}'
    TEXT_HTML_DIR = str(html_directory())
    
    # Pagination
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 500
    
    # Debug
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
