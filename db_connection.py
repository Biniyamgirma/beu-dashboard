from sqlalchemy import create_engine
import streamlit as st
import os


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

    connection_string = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"

    engine = create_engine(
        connection_string,
        connect_args={
            "charset": "utf8mb4",
            "use_unicode": True,
        },
    )

    return engine