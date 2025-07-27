# File: app.py

import os
import io
import re
import time
import json
import streamlit as st
import pandas as pd
import requests
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
    if ops.get("site") and site_filter not in ("(any)", ""):
        parts.append(f"site:{site_filter}")
    if ops.get("intitle"):
        jr = " OR ".join(f'"{r}"' for r in roles)
        parts.append(f'intitle:({jr})')
    ji = " OR ".join(f'"{i}"' for i in industries)
    jl = " OR ".join(f'"{l}"' for l in locations)
    parts.append(f'({ji})')
    parts.append(f'({jl})')
    for af in advanced_filters:
        if af:
            parts.append(af)
    return " AND ".join(parts)

# ————————————————
#  Hybrid: Python + GPT for variants
# ————————————————
@st.cache_data(show_spinner=False, ttl=3600)
def generate_queries_via_api(roles, industries, locations, engines, site_filters, advanced_filters):
    base = {
        eng: {
            sf: build_base_query(roles, industries, locations, eng, sf, advanced_filters)
            for sf in site_filters
        }
        for eng in engines
    }
    prompt = (
        "You are an expert OSINT engineer. Below are base Boolean queries:\n"
        f"{json.dumps(base)}\n"
        "For each base, generate 3 variants swapping up to 2 synonyms per Role/Industry, "
        "preserving all operators and filters, same structure. Return JSON of same shape."
    )
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
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
            with st.expander(f"{eng.upper()} queries"):
                if isinstance(buckets, dict):
                    for site, qs in buckets.items():
                        label = "Global" if site in ("", "(any)") else site
                        st.markdown(f"**{label}**")
                        for q in qs:
                            st.code(q)
                else:
                    for q in buckets:
                        st.code(q)

# ————————————————
#  Discogs → Udio Tag Builder Config
# ————————————————
BASE = "https://api.discogs.com"
UA = {"User-Agent": "DiscogsUdioTagger/0.1 (contact: you@example.com)"}
DEFAULT_MAX_TAGS = 12
SLEEP_BETWEEN = 0.6

# ————————————————
#  Discogs Tag Builder Helpers
# ————————————————
def clean_tokens(tokens):
    cleaned = []
    for t in tokens:
        t = t.strip().lower()
        if not t:
            continue
        t = re.sub(r"\s*&\s*", " and ", t)
        t = re.sub(r"[()/]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        cleaned.append(t)
    seen, out = set(), []
    for t in cleaned:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def discogs_search(token, title, artist="", year=""):
    params = {"type": "release", "per_page": 5, "token": token, "q": f"{title} {artist}".strip()}
    if year:
        params["year"] = year
    r = requests.get(f"{BASE}/database/search", headers=UA, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("results", [])

def get_release(token, rel_id):
    r = requests.get(f"{BASE}/releases/{rel_id}", headers=UA, params={"token": token}, timeout=30)
    r.raise_for_status()
    return r.json()

def score_result(r, title_low, artist_low):
    score = 0
    ttl = r.get("title","").lower()
    if ttl.startswith(title_low): score += 3
    if artist_low and artist_low in ttl: score += 2
    score += int(r.get("community",{}).get("have",0)) // 100
    return score

def choose_best(results, title, artist):
    if not results:
        return None
    return max(results, key=lambda r: score_result(r, title.lower(), artist.lower()))

def build_tag_list(rel_json, max_tags):
    styles = rel_json.get("styles",[]) or []
    genres = rel_json.get("genres",[]) or []
    year = str(rel_json.get("year","")) if rel_json.get("year") else ""
    country = rel_json.get("country","")
    formats = [f.get("name","") for f in rel_json.get("formats",[])]
    labels = [l.get("name","") for l in rel_json.get("labels",[])]
    tokens = styles + genres
    if year: tokens.append(year)
    if country: tokens.append(country)
    tokens += formats + labels
    return clean_tokens(tokens)[:max_tags]

# ————————————————
#  Natural-language line parser (enhanced)
# ————————————————
def parse_line_natively(line):
    # Try hyphen or "by" patterns
    m = re.match(r'^(?P<title>.+?)\s*[-–]\s*(?P<artist>.+?)(?:,\s*(?P<year>\d{4}s?))?$', line, re.I)
    if m:
        return m.group('title').strip(), m.group('artist').strip(), m.group('year') or ""
    m = re.match(r'^(?P<title>.+?) by (?P<artist>.+?)(?:,\s*(?P<year>\d{4}s?))?$', line, re.I)
    if m:
        return m.group('title').strip(), m.group('artist').strip(), m.group('year') or ""
    # Fallback: split on last two commas
    parts = [p.strip() for p in line.rsplit(",", 2)]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    return None

@st.cache_data(show_spinner=False, ttl=3600)
def parse_ambiguous_with_gpt(lines):
    prompt = (
        "Parse these song lines into a JSON array of {title,artist,year} (year empty if unknown):\n"
        f"{json.dumps(lines)}"
    )
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0,
    )
    return json.loads(resp.choices[0].message.content)

# ————————————————
#  Streamlit UI: Discogs → Udio Tag Builder
# ————————————————
def run_udio_tag_builder():
    st.header("🎵 Discogs → Udio Tag Builder")
    discogs_token = st.text_input("Discogs token", type="password")
    with st.expander("How to get a Discogs token", expanded=False):
        st.markdown(
            "1. Log in to Discogs\n"
            "2. Go to **Settings → Developers**\n"
            "3. Generate a personal access token\n"
            "4. Paste it above"
        )
    col1, col2 = st.columns(2)
    with col1:
        uploaded = st.file_uploader("Drop CSV/XLSX here", type=["csv","xls","xlsx"])
    with col2:
        manual = st.text_area(
            "…or paste song lines (Title - Artist, Year optional)",
            height=150,
            placeholder=(
                "Bohemian Rhapsody - Queen, 1975\n"
                "The Big Beat (Themes For Radio, Film, TV), Alan Hawkshaw, 1970s"
            )
        )
    st.divider()
    max_tags = st.slider("Max tags per line", 5, 20, DEFAULT_MAX_TAGS)
    run = st.button("Build tags", disabled=not (discogs_token and (uploaded or manual.strip())))
    if not run:
        return

    # Ingest
    if uploaded:
        try:
            raw = uploaded.read()
            uploaded.seek(0)
            if uploaded.name.lower().endswith((".xls", ".xlsx")):
                df_in = pd.read_excel(io.BytesIO(raw), dtype=str).fillna("")
            else:
                df_in = pd.read_csv(
                    io.BytesIO(raw), dtype=str, sep=None, engine="python", on_bad_lines="skip"
                ).fillna("")
            for col in ["title","artist","year"]:
                if col not in df_in.columns:
                    df_in[col] = ""
            df_in = df_in[["title","artist","year"]]
        except Exception as e:
            st.error(str(e)); return
    else:
        lines = [l for l in manual.splitlines() if l.strip()]
        parsed, ambiguous = [], []
        for line in lines:
            out = parse_line_natively(line)
            if out:
                parsed.append(out)
            else:
                ambiguous.append(line)
        if ambiguous:
            try:
                amb = parse_ambiguous_with_gpt(ambiguous)
                for item in amb:
                    parsed.append((item.get("title",""), item.get("artist",""), item.get("year","")))
            except Exception as e:
                st.error("Parsing error: " + str(e)); return
        df_in = pd.DataFrame(parsed, columns=["title","artist","year"])

    # Build tags
    out, total = [], len(df_in)
    prog = st.progress(0.0)
    for idx, row in df_in.iterrows():
        title, artist, year = row["title"], row["artist"], row["year"]
        label = f"{title} - {artist}".strip(" -")
        try:
            res = discogs_search(discogs_token, title, artist, year)
            best = choose_best(res, title, artist)
            tags = build_tag_list(get_release(discogs_token, best["id"]), max_tags) if best else ["NO_MATCH"]
        except Exception as e:
            tags = [f"ERROR: {e}"]
        out.append({"input_title": label, "udio_tags": ", ".join(tags)})
        prog.progress((idx + 1) / total)
        time.sleep(SLEEP_BETWEEN)

    df_out = pd.DataFrame(out)
    st.success("Done.")
    st.dataframe(df_out, use_container_width=True)
    st.download_button("Download CSV", df_out.to_csv(index=False), "prompts.csv", "text/csv")
    st.markdown("### Copy individual tag lines")
    for _, r in df_out.iterrows():
        st.code(r["udio_tags"])

# ————————————————
#  Main routing
# ————————————————
def main():
    st.set_page_config(page_title="Discogs→Udio", layout="wide")
    st.sidebar.header("Tool Module")
    mode = st.sidebar.selectbox("Choose module", ["Search Tools", "Udio Tag Builder"])
    if mode == "Search Tools":
        run_query_builder()
    else:
        run_udio_tag_builder()

if __name__ == "__main__":
    main()
