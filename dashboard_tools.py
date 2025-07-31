# File: dashboard_tools.py

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

def run_dashboard():
    st.title("🎯 Deadline Tracker Dashboard")

    # DEBUG: show which secrets are loaded
    st.write("🔐 Loaded secrets keys:", st.secrets.keys())

    # Read-only Sheets scope
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    gc = gspread.authorize(creds)

    # Open by key
    SHEET_ID = "11DSwvbiCCY59R8v5zE0zVmSB4zhB4LRqNX0B0LgZNmw"
    worksheet = gc.open_by_key(SHEET_ID).worksheet("Dashboard")

    # Load data
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)

    # Parse dates
    df["Due Date"]       = pd.to_datetime(df["Due Date"], errors="coerce")
    df["Date Completed"] = pd.to_datetime(df["Date Completed"], errors="coerce")

    # Sidebar filters
    with st.sidebar:
        st.header("📊 Filters")
        status_filter   = st.multiselect("Status",     options=df["Status"].unique())
        category_filter = st.multiselect("Category",   options=df["Category"].unique())
        assigned_filter = st.multiselect("Assigned To",options=df["Assigned To"].unique())

    if status_filter:
        df = df[df["Status"].isin(status_filter)]
    if category_filter:
        df = df[df["Category"].isin(category_filter)]
    if assigned_filter:
        df = df[df["Assigned To"].isin(assigned_filter)]

    # Conditional row-fill coloring
    def highlight_row(row):
        if row["Category"] == "In-House" and row["Status"] == "Active":
            bg = "yellow"
        elif row["Category"] == "Client" and row["Status"] == "Active":
            bg = "red"
        elif row["Status"] == "Approved":
            bg = "lightblue"
        elif row["Status"] == "Submitted" or row.get("Confirmed / Live?", "") == "Yes":
            bg = "white"
        else:
            bg = ""
        return [f"background-color: {bg}" for _ in row]

    styled = df.style.apply(highlight_row, axis=1)
    st.dataframe(styled, use_container_width=True)
