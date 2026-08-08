from sqlalchemy import create_engine
import streamlit as st

@st.cache_resource
def create_db_engine():
    user = "analyst"
    password = "a66ed8f80492a2cfd6c03f817b3be1eb"
    host = 'database-production-large-cluster.cluster-ro-cbiml1hzpsyo.eu-west-1.rds.amazonaws.com'
    port = 3306
    database = "beu"

    connection_string = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"

    engine = create_engine(
        connection_string,
        connect_args={
            "charset": "utf8mb4",
            "use_unicode": True,
        },
    )

    return engine