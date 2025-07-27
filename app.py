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
#  Configure OpenAI (for Search Tools & Corrections)
# ————————————————
openai.api_key = os.getenv("OPENAI_API_KEY")

# ————————————————
#  Discogs Tag Builder Config & Helpers
# ————————————————
BASE = "https://api.discogs.com"
UA = {"User-Agent": "DiscogsUdioTagger/0.1 (contact: you@example.com)"}
DEFAULT_MAX_TAGS = 12
SLEEP_BETWEEN = 0.6

def clean_tokens(tokens):
    cleaned, seen = [], set()
    for t in tokens:
        t = t.strip().lower()
        if not t:
            continue
        t = re.sub(r"\s*&\s*", " and ", t)
        t = re.sub(r"[()/]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        if t not in seen:
            seen.add(t)
            cleaned.append(t)
    return cleaned

def discogs_search(token, title, artist="", year=""):
    params = {"type": "release", "per_page": 5, "token": token, "q": f"{title} {artist}".strip()}
    if year:
        y = year.rstrip("s")
        if y.isdigit():
            params["year"] = y
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
    if title_low and ttl.startswith(title_low): score += 3
    if artist_low and artist_low in ttl: score += 2
    score += int(r.get("community",{}).get("have",0)) // 100
    return score

def choose_best(results, title, artist):
    if not results: return None
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
#  Natural-language parser (Python-first)
# ————————————————
def parse_line_natively(line):
    # Try "Title - Artist, Year"
    m = re.match(r'^(.*?)\s*[-–]\s*(.*?)(?:,\s*(\d{4}s?))?$', line)
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3) or ""
    # "Title by Artist, Year"
    m = re.match(r'^(.*?) by (.*?)(?:,\s*(\d{4}s?))?$', line, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3) or ""
    # fallback: treat whole line as title
    return line.strip(), "", ""

# ————————————————
#  GPT batched correction for unmatched
# ————————————————
@st.cache_data(show_spinner=False, ttl=3600)
def correct_unmatched(entries):
    """
    entries: list of {"index": i, "title": t, "artist": a, "year": y}
    Returns list of {"index": i, "title": t2, "artist": a2, "year": y2}.
    """
    payload = json.dumps(entries)
    prompt = (
        "You are a metadata normalizer. "
        "Given this JSON array of song entries (title, artist, year), "
        "correct any typos in title or artist according to Discogs listings. "
        "Return a JSON array of the same length with fields {index,title,artist,year}."
        f"\n\nInput:\n{payload}"
    )
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0,
    )
    return json.loads(resp.choices[0].message.content)

# ————————————————
#  File upload reader
# ————————————————
def read_uploaded_file(uploaded_file):
    name = uploaded_file.name.lower()
    raw = uploaded_file.read()
    uploaded_file.seek(0)
    try:
        if name.endswith((".xls", ".xlsx")):
            df = pd.read_excel(io.BytesIO(raw), dtype=str).fillna("")
        else:
            df = pd.read_csv(
                io.BytesIO(raw),
                dtype=str, sep=None, engine="python", on_bad_lines="skip"
            ).fillna("")
    except Exception as e:
        raise ValueError(f"Can't parse file: {e}")
    for col in ["title","artist","year"]:
        if col not in df.columns:
            df[col] = ""
    return df[["title","artist","year"]]

# ————————————————
#  Streamlit UI: Discogs → Udio Tag Builder
# ————————————————
def run_udio_tag_builder():
    st.header("🎵 Discogs → Udio Tag Builder")
    token = st.text_input("Discogs token", type="password")
    with st.expander("How to get a Discogs token", expanded=False):
        st.markdown("1. Log in to Discogs\n2. Settings → Developers → Create token\n3. Paste it above")
    col1, col2 = st.columns(2)
    with col1:
        uploaded = st.file_uploader("Drop CSV/XLSX here", type=["csv","xls","xlsx"])
    with col2:
        manual = st.text_area(
            "…or paste free-form song lines",
            height=150,
            placeholder="Bohemian Rhapsody - Queen, 1975\nThe Big Beat, Alan Hackshaw, 1970s"
        )
    st.divider()
    max_tags = st.slider("Max tags per line", 5, 20, DEFAULT_MAX_TAGS)
    run = st.button("Build tags", disabled=not (token and (uploaded or manual.strip())))
    if not run: return

    # 1) Ingest
    if uploaded:
        try:
            df_in = read_uploaded_file(uploaded)
        except Exception as e:
            st.error(str(e)); return
    else:
        rows = []
        for line in manual.splitlines():
            line = line.strip()
            if not line: continue
            t,a,y = parse_line_natively(line)
            rows.append((t,a,y))
        df_in = pd.DataFrame(rows, columns=["title","artist","year"])

    # 2) First-pass search
    unmatched = []
    out = []
    for idx, row in df_in.iterrows():
        res = discogs_search(token, row["title"], row["artist"], row["year"])
        if res:
            out.append({"idx": idx, "results": res})
        else:
            unmatched.append({"index": idx, "title": row["title"], "artist": row["artist"], "year": row["year"]})

    # 3) If any unmatched, correct them in one cheap GPT call
    if unmatched:
        corrections = correct_unmatched(unmatched)
        for corr in corrections:
            i = corr["index"]
            df_in.at[i, "title"]  = corr.get("title","")
            df_in.at[i, "artist"] = corr.get("artist","")
            df_in.at[i, "year"]   = corr.get("year","")

    # 4) Final loop: search + tag build
    prog = st.progress(0.0)
    total = len(df_in)
    out_rows = []
    for i, row in df_in.iterrows():
        title, artist, year = row["title"], row["artist"], row["year"]
        label = f"{title} - {artist}".strip(" -")
        try:
            results = discogs_search(token, title, artist, year)
            best = choose_best(results, title, artist)
            if best:
                rel = get_release(token, best["id"])
                tags = build_tag_list(rel, max_tags)
            else:
                tags = ["NO_MATCH"]
        except Exception as e:
            tags = [f"ERROR: {e}"]
        out_rows.append({"input_title": label, "udio_tags": ", ".join(tags)})
        prog.progress((i + 1) / total)
        time.sleep(SLEEP_BETWEEN)

    df_out = pd.DataFrame(out_rows)
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
    choice = st.sidebar.selectbox("Choose module", ["Search Tools", "Udio Tag Builder"])
    if choice == "Search Tools":
        st.warning("Search Tools moved to your other app module.")
    else:
        run_udio_tag_builder()

if __name__ == "__main__":
    main()
