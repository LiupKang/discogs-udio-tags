# File: app.py

import streamlit as st
from search_tools import run_query_builder
from udio_tools import run_udio_tag_builder

def main():
    st.set_page_config(page_title="Multitool App", layout="wide")
    st.sidebar.header("Tool Module")
    choice = st.sidebar.selectbox("Choose module", [
        "Search Tools",
        "Udio Tag Builder"
    ])
    if choice == "Search Tools":
        run_query_builder()
    else:
        run_udio_tag_builder()

if __name__ == "__main__":
    main()
