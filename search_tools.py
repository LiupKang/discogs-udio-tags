# File: search_tools.py

import os
import json
import re
import streamlit as st
import openai

# ————————————————
#  Configure OpenAI
# ————————————————
openai.api_key = os.getenv("OPENAI_API_KEY")

# ————————————————
#  Generate Boolean queries via API
# ————————————————
@st.cache_data(show_spinner=False, ttl=3600)
def generate_queries_via_api(roles, industries, locations, engines, site_filters):
    # Prepare quoted OR-lists
    roles_fmt      = " OR ".join(f'"{r}"' for r in roles)
    industries_fmt = " OR ".join(f'"{i}"' for i in industries)
    locations_fmt  = " OR ".join(f'"{l}"' for l in locations)

    prompt = f"""
You are an expert OSINT engineer. Using exactly these Roles, Industries and Locations:
  Roles:    {roles_fmt}
  Industries:{industries_fmt}
  Locations: {locations_fmt}

Generate 5 full Boolean search strings for each engine in {engines}.  
Each must follow this pattern:

  [site:DOMAIN if not "(any)"] intitle:({roles_fmt}) AND ({industries_fmt}) AND ({locations_fmt})

Return a JSON object with this exact shape, and **nothing else** (no markdown, no comments):

{{
  "google":     {{ "<site_filter>": ["query1", "query2", …], … }},
  "bing":       {{ … }},
  "duckduckgo": {{ … }}
}}
"""

    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )

    text = resp.choices[0].message.content.strip()
    # Strip code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Now load
    return json.loads(text)


# ————————————————
#  Streamlit UI for Query Builder
# ————————————————
def run_query_builder():
    st.header("🔍 Boolean Query Builder")

    engines = st.multiselect(
        "Select engines",
        ["google", "bing", "duckduckgo"],
        default=["google"]
    )
    site_filters = st.multiselect(
        "Site filters",
        ["(any)", "linkedin.com/in", "productionhub.com", "aicpnext.com"],
        default=["(any)", "linkedin.com/in"]
    )
    roles = st.text_input("Roles (comma-separated)", "Music Supervisor,Audio Director")
    industries = st.text_input("Industries (comma-separated)", "Advertising,Film")
    locations = st.text_input("Locations (comma-separated)", "United States,UK")

    if st.button("Generate Queries"):
        if not (roles.strip() and industries.strip() and locations.strip()):
            st.error("Fill in Roles, Industries, and Locations first.")
            return

        role_list = [r.strip() for r in roles.split(",") if r.strip()]
        ind_list  = [i.strip() for i in industries.split(",") if i.strip()]
        loc_list  = [l.strip() for l in locations.split(",") if l.strip()]

        try:
            results = generate_queries_via_api(
                role_list, ind_list, loc_list, engines, site_filters
            )
        except json.JSONDecodeError:
            st.error("Received invalid JSON from the API—please try again.")
            return
        except Exception as e:
            st.error(f"API error: {e}")
            return

        # Render
        for eng, buckets in results.items():
            with st.expander(eng.upper(), expanded=True):
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
