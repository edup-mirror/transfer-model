import os
import pandas as pd
import streamlit as st
import sqlalchemy as sa
import pydeck as pdk

# ---- Config ----
st.set_page_config(page_title="Transfer Model", layout="wide")

# Streamlit Cloud: secrets; Local: env var
from dotenv import load_dotenv

# Load local .env (no-op on Streamlit Cloud)
load_dotenv()

# Prefer local env var; fall back to Streamlit Cloud secrets if present
PG_DSN = os.environ.get("PG_DSN")
if not PG_DSN:
    try:
        PG_DSN = st.secrets["PG_DSN"]  # only exists in Cloud
    except Exception:
        PG_DSN = None

if not PG_DSN:
    st.error("No PG_DSN found. Set it in your local .env or in Streamlit Cloud Secrets.")
    st.stop()

# DB engine
engine = sa.create_engine(PG_DSN, pool_pre_ping=True)

# ---- Data helpers ----
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
             count(*) as row_count,
             max(road_restrictions) as road_restrictions,
             avg(mt_total) as mt_total,
             avg(round_trip_hours) as round_trip_hours,
             sum(baseline_num_loads) as num_loads,
             sum(baseline_transfer_hours_yr) as transfer_hours_yr,
             sum(baseline_num_loads) as baseline_num_loads,
             sum(baseline_transfer_hours_yr) as baseline_transfer_hours_yr
      from rf_static
      group by site_key, from_facility, address
      order by name
    """
    return pd.read_sql(q, engine)

@st.cache_data(ttl=30)
def fetch_material_summary():
    # Fetches the cleaned up view showing effects of material moves
    q = """
      select *
      from rf_site_summary_display
      order by "Facility", "Material Stream", "Load Name"
    """
    return pd.read_sql(q, engine)

import sqlalchemy as sa
import pandas as pd

def call_move(engine, from_key: str, to_key: str, delta: float) -> pd.DataFrame:
    sql = sa.text("""
        select *
        from public.move_material_between_sites(
            CAST(:from_key AS text),
            CAST(:to_key   AS text),
            CAST(:delta    AS numeric)
        )
    """)
    with engine.begin() as conn:
        return pd.read_sql(sql, conn, params={
            "from_key": from_key,
            "to_key": to_key,
            "delta": float(delta),
        })


def fetch_rows_for_site(engine, site_key: str) -> pd.DataFrame:
    sql = sa.text("""
      select load_name, material_stream,
             mt_total, coalesce(mt_total_override, mt_total) as mt_current,
             baseline_num_loads, current_num_loads, delta_num_loads,
             baseline_transfer_hours_yr, current_transfer_hours_yr, delta_transfer_hours_yr
      from rf_static
      where site_key = :site_key
      order by material_stream, load_name
    """)
    with engine.begin() as conn:
        return pd.read_sql(sql, conn, params={"site_key": site_key})

import sqlalchemy as sa
import pandas as pd

def reset_site(engine, site_key: str) -> int:
    sql = sa.text("select reset_site_override(CAST(:k AS text)) as rows")
    with engine.begin() as conn:
        r = pd.read_sql(sql, conn, params={"k": site_key})
    return int(r["rows"].iat[0])

def reset_all(engine) -> int:
    sql = sa.text("select reset_all_overrides() as rows")
    with engine.begin() as conn:
        r = pd.read_sql(sql, conn)
    return int(r["rows"].iat[0])


# ---- UI ----
st.title("Transfer Model")

# KPIs (from views you created in DB)
tot = fetch_totals()
c1, c2 = st.columns(2)
c1.metric("Annual Transfer Hours (Δ)", f"{tot['current_hours_annual'][0]:,.2f}", f"{tot['delta_hours_annual'][0]:+.2f}", delta_color="inverse")
c2.metric("Monthly Transfer Hours (Δ)", f"{tot['current_hours_monthly'][0]:,.2f}", f"{tot['delta_hours_monthly'][0]:+.2f}", delta_color="inverse")

# Fetch sites data for use throughout the app
sites = fetch_sites()
sites["label"] = sites["name"] + " — " + sites["address"]

# Create two-column layout for controls and map
left_col, right_col = st.columns([1, 1])

with left_col:
    st.subheader("Move material between sites")

    # Reuse the sites dataframe already loaded
    sites["label"] = sites["name"] + " — " + sites["address"]

    left, right = st.columns(2)
    from_label = left.selectbox("From site", sites["label"], key="from_site")
    to_label   = right.selectbox("To site",   sites["label"], key="to_site")

    # Get the total MT for the selected "From" site to use as default
    from_key = sites.loc[sites["label"] == from_label, "site_key"].iat[0]
    from_total_mt = sites.loc[sites["label"] == from_label, "mt_total"].iat[0]
    
    delta_mt = st.number_input("MT to move (annual)", min_value=0.0, step=10.0, value=float(from_total_mt))

    to_key   = sites.loc[sites["label"] == to_label,   "site_key"].iat[0]

    if st.button("Move material"):
        if delta_mt <= 0:
            st.error("Enter a positive MT amount.")
        elif from_key == to_key:
            st.error("From and To must be different sites.")
        else:
            try:
                res = call_move(engine, from_key, to_key, float(delta_mt))
                st.success(
                    f"Moved {delta_mt:,.2f} MT. "
                    f"From: {res['from_before'][0]:,.2f} → {res['from_after'][0]:,.2f}. "
                    f"To: {res['to_before'][0]:,.2f} → {res['to_after'][0]:,.2f}."
                )
                # refresh cached queries so KPIs & map update
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(str(e))

            st.write("Updated rows for 'From' site:")
            st.dataframe(fetch_rows_for_site(engine, from_key), use_container_width=True)

    st.subheader("Reset overrides")

    # reuse sites df already loaded; it has 'label' and 'site_key'
    col1, col2 = st.columns(2)

    sel_label = col1.selectbox("Select site to reset", sites["label"], key="reset_sel")
    sel_key = sites.loc[sites["label"] == sel_label, "site_key"].iat[0]

    if col1.button("Reset selected site"):
        try:
            n = reset_site(engine, sel_key)
            st.success(f"Reset {n} row(s) to baseline for this site.")
            st.cache_data.clear()  # refresh KPIs/map
            st.rerun()
            # Optional: show the now-baseline rows for confirmation
            st.write("Rows after reset:")
            st.dataframe(fetch_rows_for_site(engine, sel_key), use_container_width=True)
        except Exception as e:
            st.error(str(e))

    if col2.button("Reset ALL sites"):
        try:
            n = reset_all(engine)
            st.success(f"Reset {n} row(s) across all sites.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(str(e))

with right_col:
    st.subheader("Sites Map")
    st.pydeck_chart(pdk.Deck(
        map_style='road',
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
            get_color=[34, 139, 34, 200],  # Green color back
            radius_scale=0.3,  # Scale down with zoom - smaller number = more shrinkage
            radius_min_pixels=3,  # Minimum size when zoomed in
            radius_max_pixels=30,  # Maximum size when zoomed out
            pickable=True,
            stroked=True,
            stroke_width=1,
            stroke_color=[255, 255, 255, 255]
        )],
        tooltip={
            "html": "<b>Site:</b> {name}<br/>"
                   "<b>Road Restrictions:</b> {road_restrictions}<br/>"
                   "<b>Baseline Tonnage (MT):</b> {mt_total}<br/>"
                   "<b>Adjusted Round Trip Time (+2hrs +10%):</b> {round_trip_hours}<br/>"
                   "<b>Baseline Loads/year:</b> {num_loads}<br/>"
                   "<b>Baseline Transfer Hours/Year:</b> {transfer_hours_yr}",
            "style": {
                "backgroundColor": "rgba(0,0,0,0.8)",
                "color": "white",
                "fontSize": "12px",
                "padding": "10px",
                "borderRadius": "5px"
            }
        }
    ))

# Material Summary Display - shows detailed effects of material moves
st.subheader("Material Transfer Summary")
st.write("This table shows the detailed effects of material moves on each facility, load, and material stream:")

material_summary = fetch_material_summary()
st.dataframe(material_summary, use_container_width=True, height=400)
