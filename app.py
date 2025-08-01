# File: app.py

import os
from dotenv import load_dotenv
import streamlit as st
from search_tools import run_query_builder
from udio_tools   import run_udio_tag_builder

# ————————————————
#  Load local .env (for dev); in Cloud, .env is ignored.
# ————————————————
load_dotenv()  # reads .env into os.environ if present

def main():
    st.set_page_config(page_title="Discogs → Udio Multitool", layout="wide")

    # 👉 Get your keys either from Streamlit Secrets (Cloud) or env vars (local)
    # (In Cloud, set these under Settings → Secrets)
    st_secrets = st.secrets
    OPENAI_KEY   = st_secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    DISCOGS_TOKEN = st_secrets.get("DISCOGS_TOKEN")   or os.getenv("DISCOGS_TOKEN")

    # Validate
    if not OPENAI_KEY:
        st.error("Missing OpenAI API key! Add OPENAI_API_KEY to Streamlit Secrets or .env.")
        return
    if not DISCOGS_TOKEN:
        st.error("Missing Discogs token! Add DISCOGS_TOKEN to Streamlit Secrets or .env.")
        return

    # Make them available to submodules
    os.environ["OPENAI_API_KEY"] = OPENAI_KEY
    os.environ["DISCOGS_TOKEN"]   = DISCOGS_TOKEN

    st.sidebar.header("Tool Module")
    choice = st.sidebar.selectbox("Pick a tool", [
        "Search Tools",
        "Udio Tag Builder"
    ])

    if choice == "Search Tools":
        run_query_builder()
    else:
        run_udio_tag_builder()

if __name__ == "__main__":
    main()
