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
    # Format the user inputs into OR‑separated quoted lists
    roles_fmt      = " OR ".join(f'"{r}"' for r in roles)
    industries_fmt = " OR ".join(f'"{i}"' for i in industries)
    locations_fmt  = " OR ".join(f'"{l}"' for l in locations)

    prompt = f"""
You are an expert OSINT engineer. Using exactly the Roles, Industries and Locations provided below,
generate 5 full Boolean search strings for each of these engines: {engines}.  
Each string must follow this structure:

  [site:domain if site_filter != "(any)"] intitle:({roles_fmt}) AND ({industries_fmt}) AND ({locations_fmt})

– Use the site: filter only when a site_filter is not "(any)".  
– Always wrap each value in quotes, use OR between list items, and AND between the three groups.  
– Do NOT invent or substitute any other job titles, industries, or locations.

Return valid JSON mapping each engine to a dict of site_filter→list of strings, e.g.:

{{
  "google": {{
    "":    ["…global query…", …],
    "linkedin.com/in": ["…linkedin query…"]
  }},
  "bing": {{ /* same shape */ }},
  "duckduckgo": {{ /* same shape */ }}
}}
"""
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
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
        # ensure inputs are not empty
        if not (roles.strip() and industries.strip() and locations.strip()):
            st.error("Please fill in Roles, Industries, and Locations.")
            return

        role_list = [r.strip() for r in roles.split(",") if r.strip()]
        ind_list  = [i.strip() for i in industries.split(",") if i.strip()]
        loc_list  = [l.strip() for l in locations.split(",") if l.strip()]

        results = generate_queries_via_api(
            role_list, ind_list, loc_list, engines, site_filters
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
    params = {
        "artist": title,
        "release_title": artist,
        "year": year,
        "token": token
    }
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
        # dedupe
        seen = set()
        clean = []
        for t in tags:
            if t and t not in seen:
                seen.add(t)
                clean.append(t)
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
        uploaded = st.file_uploader("CSV file", type=["csv"])
        if uploaded:
            df = pd.read_csv(uploaded)
    else:
        pasted = st.text_area("Paste lines like title,artist,year")
        if pasted:
            rows = [line.split(",") for line in pasted.splitlines() if line.strip()]
            df = pd.DataFrame(rows, columns=["title", "artist", "year"])

    if df is not None and st.button("Build Tags"):
        df["tags"] = df.apply(
            lambda x: get_tags(x["title"], x["artist"], x["year"], token),
            axis=1
        )
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
