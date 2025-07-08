import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config
from sqlalchemy import create_engine
from urllib.parse import urlparse

# Initialize SQLAlchemy
db = SQLAlchemy()

def ensure_db(uri: str):
    """
    Create the PostgreSQL database if it doesn't exist by connecting to the default 'postgres'.
    """
    parsed = urlparse(uri)
    db_name = parsed.path.lstrip('/')
    admin_uri = uri.replace(f'/{db_name}', '/postgres')
    engine = create_engine(admin_uri, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(f"CREATE DATABASE {db_name}")
    engine.dispose()


def create_app():
    """
    Application factory that:
     1) Ensures the database exists,
     2) Initializes SQLAlchemy,
     3) Imports models,
     4) Creates tables,
     5) Registers routes.
    """
    app = Flask(__name__)
    app.config.from_object(Config)

    # 1) Ensure the database itself exists
    try:
        ensure_db(app.config['SQLALCHEMY_DATABASE_URI'])
    except Exception:
        pass

    # 2) Initialize SQLAlchemy
    db.init_app(app)

    # 3) Import models so SQLAlchemy knows about them
    from app import models  # no circular import, after db is defined

    # 4) Create tables for all models
    with app.app_context():
        db.create_all()

    # 5) Register blueprints / routes
    from app.views import main_bp
    app.register_blueprint(main_bp)

    return app
