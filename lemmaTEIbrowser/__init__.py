
"""lemmaTEIbrowser - A Flask application for browsing lemmatized TEI XML texts."""

__version__ = "0.1.0"

from flask import Flask, render_template
from .config import Config
from .models import init_db


def create_app(config_class=Config):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize database
    init_db(app)
    
    # Register API blueprint
    from .api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    
    # Main route
    @app.route('/')
    def index():
        return render_template('index.html')
    
    @app.route('/list')
    def list_view():
        return render_template('list.html')

    return app