# File: dashboard_tools.py

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

def run_dashboard():
    st.title("🎯 Deadline Tracker Dashboard")

    # DEBUG: which secrets are loaded
    st.write("🔐 Loaded secrets keys:", st.secrets.keys())

    # Read-only Sheets scope
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    gc = gspread.authorize(creds)

    # ——————————————
    # Use your actual Sheet ID here
    SHEET_ID = "11DSwvbiCCY59R8v5zE0zVmSB4zhB4LRqNX0B0LgZNmw"
    worksheet = gc.open_by_key(SHEET_ID).worksheet("Dashboard")
    # ——————————————

    data = worksheet.get_all_records()
    df = pd.DataFrame(data)

    # Convert dates so they sort properly
    df["Due Date"] = pd.to_datetime(df["Due Date"], errors="coerce")
    df["Date Completed"] = pd.to_datetime(df["Date Completed"], errors="coerce")

    # Sidebar filters
    with st.sidebar:
        st.header("📊 Filters")
        status_filter   = st.multiselect("Status", options=df["Status"].unique())
        category_filter = st.multiselect("Category", options=df["Category"].unique())
        assigned_filter = st.multiselect("Assigned To", options=df["Assigned To"].unique())

    # Apply filters
    if status_filter:
        df = df[df["Status"].isin(status_filter)]
    if category_filter:
        df = df[df["Category"].isin(category_filter)]
    if assigned_filter:
        df = df[df["Assigned To"].isin(assigned_filter)]

    st.dataframe(df, use_container_width=True)
