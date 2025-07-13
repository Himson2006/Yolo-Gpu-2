import os
from dotenv import load_dotenv

load_dotenv()  # reads .env in project root

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # PostgreSQL URL from env or default (used in Docker Compose)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://himsonchapagain@db:5432/yolodb"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Where uploaded videos live
    UPLOAD_FOLDER = os.path.join(basedir, "app", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024 * 1024  # 5 GB max

    # YOLO model path (override via env)
    YOLO_MODEL_PATH = os.environ.get(
        "YOLO_MODEL_PATH",
        os.path.join(basedir, "yolo_weights", "best.pt")
    )
    
    WATCH_FOLDER = os.environ.get(
        "WATCH_FOLDER",
        os.path.join(UPLOAD_FOLDER, "incoming")
    )