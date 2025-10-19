import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    
    SECRET_KEY = os.environ.get("SECRET_KEY")
    AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN")
    AUTH0_CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID")
    AUTH0_CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET")
    # PostgreSQL URL from env or default (used in Docker Compose)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://himsonchapagain@localhost:5432/yolodb"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Where uploaded videos live
    UPLOAD_FOLDER = os.path.join(basedir, "app", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024 * 1024  # 5 GB max

    YOLO_MODEL_PATH = os.environ.get(
        "YOLO_MODEL_PATH",
        os.path.join(basedir, "yolo_weights", "best.pt")
    )
    
    WATCH_FOLDER = os.environ.get(
        "WATCH_FOLDER",
        os.path.join(UPLOAD_FOLDER, "incoming")
    )