import os
import streamlit as st

st.set_page_config(page_title="Transfer Model", layout="wide")
st.title("Transfer Model — Setup Check")

dsn_present = bool(os.environ.get("PG_DSN"))
st.write("Environment variable PG_DSN set:", dsn_present)
st.info("This is just a scaffold. We’ll wire the real app after DB checks.")
