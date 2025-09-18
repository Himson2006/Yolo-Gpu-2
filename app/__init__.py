import os
from flask import Flask, session, url_for, redirect, abort
from flask_sqlalchemy import SQLAlchemy
from config import Config
from authlib.integrations.flask_client import OAuth
from functools import wraps
from sqlalchemy import create_engine, text
from urllib.parse import urlparse
import logging
from flask_migrate import Migrate


# Initialize SQLAlchemy
db = SQLAlchemy()
migrate = Migrate()
oauth = OAuth()

def ensure_db(uri: str):
    """
    Create the PostgreSQL database if it doesn't exist by connecting to the default 'postgres'.
    """
    parsed = urlparse(uri)
    db_name = parsed.path.lstrip('/')
    admin_uri = uri.replace(f'/{db_name}', '/postgres')
    engine = create_engine(admin_uri, isolation_level="AUTOCOMMIT")

    with engine.connect() as conn:
        # Check if the database already exists using text()
        result = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'"))
        if not result.fetchone():
            # THIS IS THE LINE TO FIX: Ensure CREATE DATABASE is also wrapped in text()
            conn.execute(text(f"CREATE DATABASE {db_name}"))
            logging.info(f"Database '{db_name}' created.")
        else:
            # Database already exists
            logging.info(f"Database '{db_name}' already exists.")
    engine.dispose()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Decorator to ensure the user is an admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_roles = session.get('user', {}).get('http://biocoder.edge.com/roles', [])
        if 'user' not in session or 'Admin' not in user_roles:
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function


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
    
    app.secret_key = app.config['SECRET_KEY']

    # 1) Ensure the database itself exists
    try:
        ensure_db(app.config['SQLALCHEMY_DATABASE_URI'])
    except Exception as e:
        logging.error(f"FATAL: Could not create or connect to the database. Error: {e}")

    # 2) Initialize SQLAlchemy
    db.init_app(app)
    
    migrate.init_app(app, db)
    
    # 3) Initialize Authlib
    oauth.init_app(app)
    auth0 = oauth.register(
        'auth0',
        client_id=app.config['AUTH0_CLIENT_ID'],
        client_secret=app.config['AUTH0_CLIENT_SECRET'],
        api_base_url=f"https://{app.config['AUTH0_DOMAIN']}",
        server_metadata_url=f"https://{app.config['AUTH0_DOMAIN']}/.well-known/openid-configuration",
        client_kwargs={'scope': 'openid profile email'},
    )

    # 4) Import models so SQLAlchemy knows about them
    from app import models  # no circular import, after db is defined

    # 6) Register blueprints / routes
    from app.views import main_bp
    app.register_blueprint(main_bp)
    
    @app.route('/login')
    def login():
        return auth0.authorize_redirect(redirect_uri=url_for('callback', _external=True))

    @app.route('/callback')
    def callback():
        auth0.authorize_access_token()
        resp = auth0.get('userinfo')
        userinfo = resp.json()
        session['user'] = userinfo
        return redirect('/search')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(
            f"https://{app.config['AUTH0_DOMAIN']}/v2/logout?"
            + f"client_id={app.config['AUTH0_CLIENT_ID']}&"
            + f"returnTo={url_for('main.index', _external=True)}"
        )

    return app
