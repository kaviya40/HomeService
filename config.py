import os
from urllib.parse import quote_plus

try:                                  # .env support (optional)
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def build_mongo_uri():
    """Full MONGO_URI wins. Otherwise build it from MONGO_USER / MONGO_PASSWORD / MONGO_HOST.
    With no user at all, fall back to a local MongoDB."""
    uri = os.getenv("MONGO_URI", "").strip()
    if uri:
        return uri
    user = os.getenv("MONGO_USER", "").strip()
    password = os.getenv("MONGO_PASSWORD", "")
    host = os.getenv("MONGO_HOST", "").strip()
    if not user or not host:
        return "mongodb://localhost:27017"
    scheme = "mongodb+srv" if os.getenv("MONGO_SRV", "true").lower() != "false" else "mongodb"
    # quote_plus makes special characters in the password (@ : / # ...) safe
    return f"{scheme}://{quote_plus(user)}:{quote_plus(password)}@{host}/?retryWrites=true&w=majority"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    MONGO_URI = build_mongo_uri()
    MONGO_DB = os.getenv("MONGO_DB", "homeserve_db")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
