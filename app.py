# File: app.py

import streamlit as st
from search_tools import run_query_builder
from udio_tools import run_udio_tag_builder
from dashboard_tools import run_dashboard   # 👈 Add this

def main():
    st.set_page_config(page_title="Multitool App", layout="wide")
    st.sidebar.header("Tool Module")
    choice = st.sidebar.selectbox("Choose module", [
        "Search Tools",
        "Udio Tag Builder",
        "Deadline Tracker Dashboard"   # 👈 Add to menu
    ])
    if choice == "Search Tools":
        run_query_builder()
    elif choice == "Udio Tag Builder":
        run_udio_tag_builder()
    elif choice == "Deadline Tracker Dashboard":
        run_dashboard()   # 👈 Run the dashboard

if __name__ == "__main__":
    main()
