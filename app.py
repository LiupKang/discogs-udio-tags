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
#  Engine operator support
# ————————————————
ENGINE_PROFILES = {
    "google":     {"site": True,  "intitle": True},
    "bing":       {"site": True,  "intitle": False},
    "duckduckgo": {"site": False, "intitle": False},
}

# ————————————————
#  Pure-Python base query builder
# ————————————————
def build_base_query(roles, industries, locations, engine, site_filter, advanced_filters):
    ops = ENGINE_PROFILES.get(engine, {})
    parts = []
    # site:DOMAIN
    if ops.get("site") and site_filter not in ("(any)", ""):
        parts.append(f"site:{site_filter}")
    # intitle:(roles)
    if ops.get("intitle"):
        joined_roles = " OR ".join(f'"{r}"' for r in roles)
        parts.append(f'intitle:({joined_roles})')
    # (industries) AND (locations)
    joined_inds = " OR ".join(f'"{i}"' for i in industries)
    joined_locs = " OR ".join(f'"{l}"' for l in locations)
    parts.append(f'({joined_inds})')
    parts.append(f'({joined_locs})')
    # advanced filters
    for af in advanced_filters:
        if af:
            parts.append(af)
    # glue with AND
    return " AND ".join(parts)

# ————————————————
#  Hybrid: Python + GPT for variants
# ————————————————
@st.cache_data(show_spinner=False, ttl=3600)
def generate_queries_via_api(roles, industries, locations, engines, site_filters, advanced_filters):
    # 1) build base queries
    base = {
        eng: {
            sf: build_base_query(roles, industries, locations, eng, sf, advanced_filters)
            for sf in site_filters
        }
        for eng in engines
    }
    # 2) prompt GPT to produce variants
    prompt = f"""
You are an expert OSINT engineer. Below are base Boolean queries for each engine and site filter:
{json.dumps(base, indent=2)}

For each base query, generate 3 variants that:
- Swap in up to 2 synonyms per Role and per Industry.
- Preserve all operators and advanced filters exactly.
- Keep the same site filter and engine-specific syntax.

Return valid JSON with the same shape:
{{
  "google":     {{ <site_filter>: ["var1","var2","var3"], … }},
  "bing":       {{ … }},
  "duckduckgo": {{ … }}
}}
"""
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0,
    )
    return json.loads(resp.choices[0].message.content)

# ————————————————
#  Streamlit UI: Boolean Query Builder
# ————————————————
def run_query_builder():
    st.header("🔍 Boolean Query Builder")
    engines = st.multiselect("Select engines",
                             ["google", "bing", "duckduckgo"],
                             default=["google"])
    site_filters = st.multiselect("Site filters",
                                  ["(any)", "linkedin.com/in", "productionhub.com", "aicpnext.com"],
                                  default=["(any)", "linkedin.com/in"])
    roles = st.text_input("Roles (comma-separated)", "Music Supervisor,Audio Director")
    industries = st.text_input("Industries (comma-separated)", "Advertising,Film")
    locations = st.text_input("Locations (comma-separated)", "United States,UK")
    adv_text = st.text_input("Advanced filters (comma-separated)", "-Spotify,filetype:pdf,AROUND(5)")

    if st.button("Generate Queries"):
        # validate
        if not (roles.strip() and industries.strip() and locations.strip()):
            st.error("Please fill in Roles, Industries, and Locations.")
            return
        role_list = [r.strip() for r in roles.split(",") if r.strip()]
        ind_list  = [i.strip() for i in industries.split(",") if i.strip()]
        loc_list  = [l.strip() for l in locations.split(",") if l.strip()]
        adv_list  = [f.strip() for f in adv_text.split(",") if f.strip()]

        results = generate_queries_via_api(
            role_list, ind_list, loc_list, engines, site_filters, adv_list
        )

        for eng, buckets in results.items():
            with st.expander(f"{eng.upper()} queries", expanded=True):
                if isinstance(buckets, dict):
                    for site, qs in buckets.items():
                        label = "Global" if site in ("", "(any)") else site
                        st.markdown(f"**{label}**")
                        for q in qs:
                            st.code(q)
                elif isinstance(buckets, list):
                    for q in buckets:
                        st.code(q)
                else:
                    st.write(buckets)

# ————————————————
#  Streamlit UI: Discogs → Udio Tag Builder
# ————————————————
def get_tags(title, artist, year, token):
    url = "https://api.discogs.com/database/search"
    params = {"artist": title, "release_title": artist, "year": year, "token": token}
    try:
        r = requests.get(url, params=params, timeout=10); r.raise_for_status()
        res = r.json().get("results", [])[0]
        tags = []
        for key in ("style","genre","format","label"):
            vals = res.get(key)
            if isinstance(vals, list):
                tags.extend(vals)
            elif vals:
                tags.append(vals)
        seen, clean = set(), []
        for t in tags:
            ts = str(t).strip()
            if ts and ts not in seen:
                seen.add(ts); clean.append(ts)
        return ", ".join(clean)
    except Exception:
        return ""

def run_udio_tag_builder():
    st.header("🎵 Discogs → Udio Tag Builder")
    token = st.text_input("Discogs API Token", type="password")
    st.markdown("Upload a CSV (title,artist,year) or paste lines.")
    mode = st.radio("", ["Upload CSV","Paste Data"])
    df = None
    if mode == "Upload CSV":
        up = st.file_uploader("CSV file", type=["csv"])
        if up: df = pd.read_csv(up)
    else:
        txt = st.text_area("Paste lines like title,artist,year")
        if txt:
            rows = [l.split(",") for l in txt.splitlines() if l.strip()]
            df = pd.DataFrame(rows, columns=["title","artist","year"])
    if df is not None and st.button("Build Tags"):
        df["tags"] = df.apply(lambda x: get_tags(x.title, x.artist, x.year, token), axis=1)
        st.dataframe(df)
        st.download_button("Download prompts.csv", df.to_csv(index=False), "prompts.csv")

# ————————————————
#  Main app
# ————————————————
def main():
    st.set_page_config(page_title="Discogs→Udio", layout="wide")
    st.sidebar.header("Tool Module")
    module = st.sidebar.selectbox("Choose module", ["Search Tools","Udio Tags"])
    if module=="Search Tools":
        run_query_builder()
    else:
        run_udio_tag_builder()

if __name__=="__main__":
    main()
