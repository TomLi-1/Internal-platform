import os

from dotenv import load_dotenv

load_dotenv()


def get_database_url():
    url = os.getenv("DB_URL") or os.getenv("DATABASE_URL")
    if not url:
        return None
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url
