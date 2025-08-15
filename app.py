import os
import streamlit as st
from dotenv import load_dotenv
import sqlalchemy as sa

st.set_page_config(page_title="Transfer Model", layout="wide")
st.title("Transfer Model — Setup Check")

# Load .env so PG_DSN is available locally
load_dotenv()

from sqlalchemy import make_url
dsn = os.environ.get("PG_DSN")
st.write("Raw DSN repr:", repr(dsn))  # catches hidden spaces/newlines/quotes
if dsn:
    url = make_url(dsn)
    st.write("Driver parsed:", url.drivername)   # should be 'postgresql+psycopg'
    st.write("Host parsed:  ", url.host)         # should be 'db.<project-ref>.supabase.co'
    st.write("Port parsed:  ", url.port)         # should be 5432


dsn = os.environ.get("PG_DSN")
st.write("Environment variable PG_DSN set:", bool(dsn))

# Minimal DB connectivity test
ok = False
err = None
if dsn:
    try:
        engine = sa.create_engine(dsn, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(sa.text("select 1"))
        ok = True
    except Exception as e:
        err = str(e)

st.write("Database connectivity:", "OK ✅" if ok else "FAILED ❌")
if err:
    st.error(err)

st.info("If PG_DSN is False or connectivity fails, double-check your URI and that sslmode=require is present.")
