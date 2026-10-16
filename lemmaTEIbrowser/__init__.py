
"""lemmaTEIbrowser - A Flask application for browsing lemmatized TEI XML texts."""

__version__ = "0.1.0"

from flask import Flask, render_template, send_from_directory
from .config import Config
from .models import init_db


def create_app(config_class=Config, *, config_overrides=None):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    if config_overrides:
        app.config.update(config_overrides)
    
    # Initialize database
    init_db(app)
    
    # Register API blueprint
    from .api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    
    # Main route
    @app.route('/')
    def index():
        return render_template('list.html')

    @app.route('/static/texts/<path:filename>')
    def full_text(filename):
        directory = app.config.get('TEXT_HTML_DIR') or f'{app.static_folder}/texts'
        return send_from_directory(directory, filename)

    return app
