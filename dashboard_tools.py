import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

def run_dashboard():
    st.title("🎯 Deadline Tracker Dashboard")

    # Authenticate and load Google Sheet
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"])
    gc = gspread.authorize(creds)

    SHEET_NAME = "Deadline Tracker"
    TAB_NAME = "Dashboard"
    worksheet = gc.open(SHEET_NAME).worksheet(TAB_NAME)
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)

    df['Due Date'] = pd.to_datetime(df['Due Date'], errors='coerce')
    df['Date Completed'] = pd.to_datetime(df['Date Completed'], errors='coerce')

    # Sidebar filters
    with st.sidebar:
        st.header("📊 Filters")
        status_filter = st.multiselect("Status", options=df['Status'].unique())
        category_filter = st.multiselect("Category", options=df['Category'].unique())
        assigned_filter = st.multiselect("Assigned To", options=df['Assigned To'].unique())

    if status_filter:
        df = df[df['Status'].isin(status_filter)]
    if category_filter:
        df = df[df['Category'].isin(category_filter)]
    if assigned_filter:
        df = df[df['Assigned To'].isin(assigned_filter)]

    st.dataframe(df, use_container_width=True)
