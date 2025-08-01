# File: search_tools.py

import os
import json
import re
import streamlit as st
import openai

# ————————————————
#  Configure OpenAI from env or Streamlit secrets
# ————————————————
openai.api_key = (
    st.secrets.get("OPENAI_API_KEY")
    or os.getenv("OPENAI_API_KEY")
)

@st.cache_data(show_spinner=False, ttl=3600)
def generate_queries_via_api(roles, industries, locations, engines, site_filters):
    # Build the OR-joined lists
    roles_fmt      = " OR ".join(f'"{r}"' for r in roles)
    industries_fmt = " OR ".join(f'"{i}"' for i in industries)
    locations_fmt  = " OR ".join(f'"{l}"' for l in locations)

    prompt = f"""
You are an expert OSINT engineer. Using exactly these lists:

Roles:    {roles_fmt}
Industries:{industries_fmt}
Locations: {locations_fmt}

Generate **5** Boolean search strings for each engine in {engines}.  
Use this pattern exactly:

  [site:DOMAIN if not "(any)"] intitle:({roles_fmt}) AND ({industries_fmt}) AND ({locations_fmt})

Return **only** valid JSON shaped like:

{{
  "google":     {{ "<site_filter>": ["q1","q2",…], … }},
  "bing":       {{ … }},
  "duckduckgo": {{ … }}
}}
"""

    # === NEW: use the v1.0+ API call ===
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )

    text = resp.choices[0].message.content.strip()
    # strip triple‐backticks if GPT wrapped the JSON
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)

def run_query_builder():
    st.header("🔍 Boolean Query Builder")
    engines = st.multiselect("Select engines", ["google", "bing", "duckduckgo"], default=["google"])
    sites   = st.multiselect("Site filters", ["(any)", "linkedin.com/in", "productionhub.com"], default=["(any)"])
    roles   = st.text_input("Roles (comma-separated)",     "Music Supervisor,Audio Director")
    inds    = st.text_input("Industries (comma-separated)","Advertising,Film")
    locs    = st.text_input("Locations (comma-separated)", "United States,UK")

    if st.button("Generate Queries"):
        rlist = [r.strip() for r in roles.split(",") if r.strip()]
        ilist = [i.strip() for i in inds.split(",")   if i.strip()]
        llist = [l.strip() for l in locs.split(",")   if l.strip()]

        try:
            results = generate_queries_via_api(rlist, ilist, llist, engines, sites)
        except Exception as e:
            st.error(f"API error: {e}")
            return

        for eng, bucket in results.items():
            with st.expander(eng.upper(), expanded=True):
                if isinstance(bucket, dict):
                    for site, qs in bucket.items():
                        label = "Global" if site in ("","(any)") else site
                        st.markdown(f"**{label}**")
                        for q in qs:
                            st.code(q)
                else:
                    for q in bucket:
                        st.code(q)
