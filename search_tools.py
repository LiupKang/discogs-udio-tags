# File: search_tools.py

import os
import json
import re
import streamlit as st
import openai

# ————————————————
#  Configure OpenAI
# ————————————————
openai.api_key = (
    st.secrets.get("OPENAI_API_KEY")
    or os.getenv("OPENAI_API_KEY")
)

@st.cache_data(show_spinner=False, ttl=3600)
def generate_base_queries(roles, industries, locations, engines):
    """
    Ask GPT for 5 global Boolean queries per engine.
    No site filters here—those get added in Python later.
    """
    roles_fmt      = " OR ".join(f'"{r}"' for r in roles)
    industries_fmt = " OR ".join(f'"{i}"' for i in industries)
    locations_fmt  = " OR ".join(f'"{l}"' for l in locations)

    prompt = f"""
You are an expert OSINT engineer. Using exactly these lists:
Roles:     {roles_fmt}
Industries:{industries_fmt}
Locations: {locations_fmt}

Generate **5** Boolean search strings for each of these engines: {engines}.
Each string must follow this pattern exactly:

  intitle:({roles_fmt}) AND ({industries_fmt}) AND ({locations_fmt})

Return **only** valid JSON in this shape (no markdown, no commentary):

{{
  "google":     ["query1", "query2", …],
  "bing":       ["…"],
  "duckduckgo": ["…"]
}}
"""
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )

    text = resp.choices[0].message.content.strip()
    # Strip ``` fences if any
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def run_query_builder():
    st.header("🔍 Boolean Query Builder")
    engines     = st.multiselect("Select engines",     ["google", "bing", "duckduckgo"], default=["google"])
    site_filters= st.multiselect("Site filters",      ["(any)", "linkedin.com/in", "productionhub.com"], default=["(any)"])
    roles       = st.text_input("Roles (comma-separated)",     "Music Supervisor,Audio Director")
    industries  = st.text_input("Industries (comma-separated)","Advertising,Film")
    locations   = st.text_input("Locations (comma-separated)", "United States,UK")

    if st.button("Generate Queries"):
        # parse inputs
        rlist = [r.strip() for r in roles.split(",")     if r.strip()]
        ilist = [i.strip() for i in industries.split(",")if i.strip()]
        llist = [l.strip() for l in locations.split(",") if l.strip()]

        # get the base, global queries
        try:
            base = generate_base_queries(rlist, ilist, llist, engines)
        except Exception as e:
            st.error(f"API error: {e}")
            return

        # now render per-engine, per-site-filter
        for eng in engines:
            with st.expander(eng.upper(), expanded=True):
                queries = base.get(eng, [])
                for site in site_filters:
                    label = "Global" if site in ("", "(any)") else site
                    st.markdown(f"**{label}**")
                    if site in ("", "(any)"):
                        # show the raw queries
                        for q in queries:
                            st.code(q)
                    else:
                        # prefix each with site:…
                        for q in queries:
                            st.code(f"site:{site} {q}")
