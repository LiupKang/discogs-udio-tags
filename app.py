# File: app.py

import os
from dotenv import load_dotenv

import streamlit as st
from search_tools import run_query_builder
from udio_tools   import run_udio_tag_builder
from dashboard_tools import run_dashboard

# ————————————————
#  Local dev: load .env
# ————————————————
load_dotenv()  # if you have a .env locally

def main():
    st.set_page_config(page_title="Multitool App", layout="wide")
    st.sidebar.header("Tool Module")
    choice = st.sidebar.selectbox("Choose module", [
        "Search Tools",
        "Udio Tag Builder",
        "Deadline Tracker Dashboard"
    ])

    if choice == "Search Tools":
        run_query_builder()
    elif choice == "Udio Tag Builder":
        run_udio_tag_builder()
    else:
        run_dashboard()

if __name__ == "__main__":
    main()
