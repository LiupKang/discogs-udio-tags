# File: app.py

import os
import json
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import dns.resolver
import openai

# ————————————————
#  Configure OpenAI
# ————————————————
openai.api_key = os.getenv("OPENAI_API_KEY")


# ————————————————
#  1) Search Tools: OpenAI‑powered Boolean Query Builder
# ————————————————
@st.cache_data(show_spinner=False, ttl=3600)
def generate_queries_via_api(roles, industries, locations, engines, site_filters):
    prompt = f"""
You are an expert OSINT engineer. Generate 5 concise, _full_ Boolean search strings for each engine in {engines}, matching this pattern:

  • site:linkedin.com/in intitle:(“Role1” OR “Role2”) AND (“Industry1” OR “Industry2”) AND “Location”

Example for “Music Supervisor, Audio Director” in “Advertising, Film” for “United States” on Google:

  site:linkedin.com/in intitle:(“Music Supervisor” OR “Audio Director”) AND (“Advertising” OR “Film”) AND “United States”

Now produce 5 queries _exactly_ like that for each engine and each domain in {site_filters}. Return valid JSON in this shape:

{{
  "google": {{
    "": ["site:linkedin.com/in intitle:(“Role1” OR “Role2”) AND (“Industry1” OR “Industry2”) AND “Location”", …],
    "linkedin.com/in": ["…"],
    "productionhub.com": ["…"]
  }},
  "bing": {{ … }},
  "duckduckgo": {{ … }}
}}
"""
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return json.loads(resp.choices[0].message.content)


def run_query_builder():
    st.header("🔍 Boolean Query Builder (OpenAI‑powered)")

    engines = st.multiselect(
        "Select engines",
        ["google", "bing", "duckduckgo"],
        default=["google"]
    )
    site_filters = st.multiselect(
        "Site filters",
        ["(any)", "linkedin.com/in", "productionhub.com", "aicpnext.com"],
        default=["(any)", "linkedin.com/in"],
    )
    roles = st.text_input("Roles (comma‑separated)", "Music Supervisor,Audio Director")
    industries = st.text_input("Industries", "Advertising,Film")
    locations = st.text_input("Locations", "United States,UK")

    if st.button("Generate Queries"):
        # Validation guard
        if not roles.strip() or not industries.strip() or not locations.strip():
            st.error("Please fill in Roles, Industries, and Locations before generating queries.")
            return

        role_list = [r.strip() for r in roles.split(",") if r.strip()]
        ind_list = [i.strip() for i in industries.split(",") if i.strip()]
        loc_list = [l.strip() for l in locations.split(",") if l.strip()]

        results = generate_queries_via_api(
            role_list,
            ind_list,
            loc_list,
            engines,
            site_filters
        )

        for eng, buckets in results.items():
            with st.expander(f"{eng.upper()} queries", expanded=True):
                if isinstance(buckets, dict):
                    for site, qs in buckets.items():
                        label = "Global" if site in ("", "(any)") else site
                        st.markdown(f"**{label}**")
                        for q in qs:
                            st.code(q, language="bash")
                elif isinstance(buckets, list):
                    for q in buckets:
                        st.code(q, language="bash")
                else:
                    st.write(buckets)


# ————————————————
#  2) Udio‑Tag Builder
# ————————————————
def get_tags(title, artist, year, token):
    url = "https://api.discogs.com/database/search"
    params = {"artist": artist, "release_title": title, "year": year, "token": token}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        res = r.json().get("results", [])[0]
        tags = []
        for key in ("style", "genre", "format", "label"):
            vals = res.get(key)
            if isinstance(vals, list):
                tags.extend(vals)
            elif vals:
                tags.append(vals)
        seen = set()
        clean = []
        for t in tags:
            ts = str(t).strip()
            if ts and ts not in seen:
                seen.add(ts)
                clean.append(ts)
        return ", ".join(clean)
    except Exception:
        return ""


def run_udio_tag_builder():
    st.header("🎵 Discogs → Udio Tag Builder")
    token = st.text_input("Discogs API Token", type="password")
    st.markdown("Upload a CSV (title,artist,year) or paste lines.")
    mode = st.radio("", ["Upload CSV", "Paste Data"])
    df = None

    if mode == "Upload CSV":
        up = st.file_uploader("CSV file", type=["csv"])
        if up:
            df = pd.read_csv(up)
    else:
        txt = st.text_area("Paste lines like title,artist,year")
        if txt:
            rows = [l.split(",") for l in txt.splitlines() if l.strip()]
            df = pd.DataFrame(rows, columns=["title", "artist", "year"])

    if df is not None and st.button("Build Tags"):
        df["tags"] = df.apply(lambda x: get_tags(x.title, x.artist, x.year, token), axis=1)
        st.dataframe(df)
        st.download_button("Download prompts.csv", df.to_csv(index=False), "prompts.csv")


# ————————————————
#  Main routing
# ————————————————
def main():
    st.set_page_config(page_title="Discogs→Udio", layout="wide")
    st.sidebar.header("Tool Module")
    module = st.sidebar.selectbox("Choose module", ["Search Tools", "Udio Tags"])

    if module == "Search Tools":
        run_query_builder()
    else:
        run_udio_tag_builder()


if __name__ == "__main__":
    main()
