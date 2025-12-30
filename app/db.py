from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from .settings import DATABASE_URL

@contextmanager
def get_conn():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
