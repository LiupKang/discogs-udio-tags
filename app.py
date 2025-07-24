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
You are an expert OSINT engineer. For each engine in {engines}, generate 5 concise Boolean search strings
to find public professional contacts.

Instructions:
- Roles: {roles}
- Industries: {industries}
- Locations: {locations}
- Produce queries both globally (no site filter) and for each of these domains: {site_filters}.
- Use only the operators each engine supports.
- Return valid JSON in this shape:
{{
  "google": {{
    "": ["global query1", "global query2", ...],
    "linkedin.com/in": ["..."],
    "productionhub.com": ["..."]
  }},
  "bing": {{ ... }},
  "duckduckgo": {{ ... }}
}}
"""
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return json.loads(resp.choices[0].message.content)


def run_query_builder():
    st.header("🔍 Boolean Query Builder (OpenAI‑powered)")
    engines = st.multiselect("Select engines", ["google", "bing", "duckduckgo"], default=["google"])
    site_filters = st.multiselect(
        "Site filters",
        ["(any)", "linkedin.com/in", "productionhub.com", "aicpnext.com"],
        default=["(any)", "linkedin.com/in"],
    )
    roles = st.text_input("Roles (comma‑separated)", "Music Supervisor,Audio Director")
    industries = st.text_input("Industries", "Advertising,Film")
    locations = st.text_input("Locations", "United States,UK")

    if st.button("Generate Queries"):
        role_list = [r.strip() for r in roles.split(",") if r.strip()]
        ind_list = [i.strip() for i in industries.split(",") if i.strip()]
        loc_list = [l.strip() for l in locations.split(",") if l.strip()]

        results = generate_queries_via_api(role_list, ind_list, loc_list, engines, site_filters)

        for eng, buckets in results.items():
            with st.expander(f"{eng.upper()} queries", expanded=True):
                for site, qs in buckets.items():
                    label = "Global" if site in ("", "(any)") else site
                    st.markdown(f"**{label}**")
                    for q in qs:
                        st.code(q, language="bash")


# ————————————————
#  2) DIY Lead Generation (fall‑back, local)
# ————————————————
def generate_boolean_queries(titles, industries, locations):
    queries = []
    for t in titles:
        for i in industries:
            for l in locations:
                queries.append(f'site:linkedin.com/in intitle:"{t.strip()}" "{i.strip()}" "{l.strip()}"')
    return queries

def scrape_team_page(url):
    contacts = []
    try:
        r = requests.get(url, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")
        domain = url.split("//")[-1].split("/")[0]
        for member in soup.select(".team-member"):
            name_el = member.select_one(".name")
            role_el = member.select_one(".role")
            mail_el = member.select_one("a[href^='mailto:']")
            name = name_el.get_text(strip=True) if name_el else ""
            role = role_el.get_text(strip=True) if role_el else ""
            email = mail_el["href"].split(":",1)[1] if mail_el else ""
            contacts.append({"name":name, "role":role, "company_domain":domain, "email":email})
    except Exception:
        pass
    return contacts

def permute_emails(first, last, domain):
    patterns = ["{f}.{l}@{d}", "{f}{l}@{d}", "{f}@{d}", "{fi}{l}@{d}"]
    f, l = first.lower(), last.lower()
    fi = f[:1]
    return {
        p.format(f=f, l=l, fi=fi, d=domain)
        for p in patterns
    }

def verify_email(email):
    try:
        dns.resolver.resolve(email.split("@")[1], "MX")
        return True
    except:
        return False

def assemble_contacts(raw):
    rows = []
    for c in raw:
        parts = c["name"].split()
        first, last = (parts + [""])[:2]
        candidates = permute_emails(first, last, c["company_domain"])
        valid = [e for e in candidates if verify_email(e)]
        chosen = valid[0] if valid else c["email"]
        rows.append({
            "name": c["name"],
            "role": c["role"],
            "company_domain": c["company_domain"],
            "email": chosen
        })
    return pd.DataFrame(rows)


def run_lead_generation():
    st.header("🧩 DIY Lead Generation")
    sub = st.radio("Function", ["Boolean Queries", "Team‑Page Scraper"])
    if sub == "Boolean Queries":
        titles = st.text_input("Titles (comma‑sep)", "Music Supervisor,Audio Director").split(",")
        industries = st.text_input("Industries", "Advertising,Film").split(",")
        locations = st.text_input("Locations", "United States").split(",")
        if st.button("Generate DIY Queries"):
            qs = generate_boolean_queries(titles, industries, locations)
            for q in qs:
                st.code(q)
    else:
        urls = st.text_area("Team Page URLs (one per line)").splitlines()
        if st.button("Scrape Team Pages"):
            raw = []
            for u in urls:
                raw.extend(scrape_team_page(u))
            df = assemble_contacts(raw)
            st.dataframe(df)
            st.download_button("Download leads.csv", df.to_csv(index=False), "leads.csv")


# ————————————————
# 3) Udio‑Tag Builder (unchanged)
# ————————————————
def get_tags(title, artist, year, token):
    url = "https://api.discogs.com/database/search"
    params = {"artist": artist, "release_title": title, "year": year, "token": token}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        res = r.json().get("results", [])[0]
        tags = []
        for key in ("style","genre","format","label"):
            vals = res.get(key)
            if isinstance(vals, list):
                tags += vals
            elif vals:
                tags.append(vals)
        seen = set(); clean = []
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
    if mode=="Upload CSV":
        up = st.file_uploader("CSV file", type=["csv"])
        if up: df = pd.read_csv(up)
    else:
        txt = st.text_area("paste lines like title,artist,year")
        if txt:
            rows = [l.split(",") for l in txt.splitlines() if l.strip()]
            df = pd.DataFrame(rows, columns=["title","artist","year"])
    if df is not None and st.button("Build Tags"):
        df["tags"] = df.apply(lambda x: get_tags(x.title, x.artist, x.year, token), axis=1)
        st.dataframe(df)
        st.download_button("Download prompts.csv", df.to_csv(index=False), "prompts.csv")


# ————————————————
# Main app routing
# ————————————————
def main():
    st.set_page_config(page_title="Discogs→Udio & Lead Gen", layout="wide")
    st.sidebar.header("Tool Module")
    module = st.sidebar.selectbox("Choose module", [
        "Search Tools",
        "DIY Lead Generation",
        "Udio Tags"
    ])
    if module == "Search Tools":
        run_query_builder()
    elif module == "DIY Lead Generation":
        run_lead_generation()
    else:
        run_udio_tag_builder()


if __name__ == "__main__":
    main()
