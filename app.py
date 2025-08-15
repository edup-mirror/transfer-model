import os
import pandas as pd
import streamlit as st
import sqlalchemy as sa
import pydeck as pdk

# ---- Config ----
st.set_page_config(page_title="Transfer Model", layout="wide")

# Streamlit Cloud: secrets; Local: env var
PG_DSN = os.getenv("PG_DSN") or st.secrets.get("PG_DSN")
if not PG_DSN:
    st.stop()

# DB engine
engine = sa.create_engine(PG_DSN, pool_pre_ping=True)

# ---- Data helpers ----
@st.cache_data(ttl=15)
def fetch_totals():
    return pd.read_sql("select * from rf_overall_totals", engine)

@st.cache_data(ttl=30)
def fetch_sites():
    # Groups rows by site_key to one point per site
    q = """
      select site_key,
             from_facility as name,
             address,
             avg(lat) as lat,
             avg(lon) as lon,
             count(*) as row_count
      from rf_static
      group by site_key, from_facility, address
      order by name
    """
    return pd.read_sql(q, engine)

# ---- UI ----
st.title("Transfer Model")

# KPIs (from views you created in DB)
tot = fetch_totals()
c1, c2, c3 = st.columns(3)
c1.metric("Annual Loads (Δ)", f"{tot['current_loads_annual'][0]:,.2f}", f"{tot['delta_loads_annual'][0]:+.2f}")
c2.metric("Annual Hours (Δ)", f"{tot['current_hours_annual'][0]:,.2f}", f"{tot['delta_hours_annual'][0]:+.2f}")
c3.metric("Monthly Hours (Δ)", f"{tot['current_hours_monthly'][0]:,.2f}", f"{tot['delta_hours_monthly'][0]:+.2f}")

# Map
sites = fetch_sites()
sites["label"] = sites["name"] + " — " + sites["address"]

st.subheader("Sites Map")
st.pydeck_chart(pdk.Deck(
    initial_view_state=pdk.ViewState(
        latitude=float(sites["lat"].mean()),
        longitude=float(sites["lon"].mean()),
        zoom=6
    ),
    layers=[pdk.Layer(
        "ScatterplotLayer",
        data=sites,
        get_position='[lon, lat]',
        get_radius=6000,
        pickable=True
    )],
    tooltip={"text": "{name}\n{address}\nRows: {row_count}"}
))

# Read-only table below (nice for sanity)
with st.expander("Site list"):
    st.dataframe(sites[["name","address","row_count","lat","lon"]], use_container_width=True)
