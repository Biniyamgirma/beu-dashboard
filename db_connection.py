from sqlalchemy import create_engine
import streamlit as st
import os

# Try to prefer the mysql-connector driver, otherwise fall back to PyMySQL.
# Hosts often omit mysql-connector; supporting both makes the app more portable.
try:
    import mysql.connector  # type: ignore
    _DBAPI_DRIVER = "mysqlconnector"
except Exception:
    try:
        import pymysql  # type: ignore

        _DBAPI_DRIVER = "pymysql"
    except Exception:
        _DBAPI_DRIVER = None


@st.cache_resource
def create_db_engine():
    """Create a SQLAlchemy engine using credentials from Streamlit secrets or env vars.

    Place a file at `.streamlit/secrets.toml` with:
    [mysql]
    user = "..."
    password = "..."
    host = "..."
    port = 3306
    database = "..."
    """
    # Load DB credentials from Streamlit secrets, with env var fallbacks
    mysql = getattr(st, "secrets", {}).get("mysql", {})
    user = mysql.get("user") or os.environ.get("DB_USER") 
    password = mysql.get("password") or os.environ.get("DB_PASSWORD") 
    host = mysql.get("host") or os.environ.get("DB_HOST")
    port = mysql.get("port") or os.environ.get("DB_PORT") or 3306
    database = mysql.get("database") or os.environ.get("DB_NAME") 

    try:
        port = int(port)
    except Exception:
        port = 3306

    if not password:
        raise RuntimeError(
            "Database password is empty. Add it to .streamlit/secrets.toml under [mysql] or set DB_PASSWORD env var."
        )

    if _DBAPI_DRIVER is None:
        raise RuntimeError(
            "No MySQL DB-API driver found. Install 'mysql-connector-python' or 'PyMySQL' and add it to your requirements."
        )

    connection_string = f"mysql+{_DBAPI_DRIVER}://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"

    engine = create_engine(
        connection_string,
        connect_args={
            "charset": "utf8mb4",
            "use_unicode": True,
        },
        pool_pre_ping=True,
    )

    return engine