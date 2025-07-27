# File: udio_tools.py

import io
import re
import time
import streamlit as st
import pandas as pd
import requests

# ————————————————
#  Discogs API config
# ————————————————
BASE = "https://api.discogs.com"
UA = {"User-Agent": "DiscogsUdioTagger/0.1 (contact: you@example.com)"}
DEFAULT_MAX_TAGS = 12
SLEEP_BETWEEN = 0.6

# ————————————————
#  Helpers
# ————————————————
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
    r = requests.get(f"{BASE}/database/search", headers=UA, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("results", [])

def get_release(token, rel_id):
    r = requests.get(f"{BASE}/releases/{rel_id}", headers=UA, params={"token": token}, timeout=10)
    r.raise_for_status()
    return r.json()

def score_result(r, title_low, artist_low):
    ttl = r.get("title","").lower()
    score = 3 if title_low and ttl.startswith(title_low) else 0
    if artist_low and artist_low in ttl:
        score += 2
    score += int(r.get("community",{}).get("have",0)) // 100
    return score

def choose_best(results, title, artist):
    if not results:
        return None
    return max(results, key=lambda r: score_result(r, title.lower(), artist.lower()))

def build_tag_list(rel_json, max_tags):
    styles = rel_json.get("styles",[]) or []
    genres = rel_json.get("genres",[]) or []
    year   = str(rel_json.get("year","")) if rel_json.get("year") else ""
    country= rel_json.get("country","")
    formats=[f.get("name","") for f in rel_json.get("formats",[])]
    labels =[l.get("name","") for l in rel_json.get("labels",[])]
    tokens = styles + genres
    if year:   tokens.append(year)
    if country:tokens.append(country)
    tokens += formats + labels
    return clean_tokens(tokens)[:max_tags]

def read_uploaded_file(uploaded_file):
    name = uploaded_file.name.lower()
    raw  = uploaded_file.read()
    uploaded_file.seek(0)
    try:
        if name.endswith((".xls", ".xlsx")):
            df = pd.read_excel(io.BytesIO(raw), dtype=str).fillna("")
        else:
            df = pd.read_csv(
                io.BytesIO(raw),
                dtype=str,
                sep=None,
                engine="python",
                on_bad_lines="skip"
            ).fillna("")
    except Exception as e:
        raise ValueError(f"Can't parse file: {e}")
    for col in ["title","artist","year"]:
        if col not in df.columns:
            df[col] = ""
    return df[["title","artist","year"]]

def read_manual_paste(text):
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        rows.append((
            parts[0] if len(parts)>0 else "",
            parts[1] if len(parts)>1 else "",
            parts[2] if len(parts)>2 else ""
        ))
    return pd.DataFrame(rows, columns=["title","artist","year"]).fillna("")

# ————————————————
#  UI
# ————————————————
def run_udio_tag_builder():
    st.header("🎵 Discogs → Udio Tag Builder")
    token = st.text_input("Discogs API Token", type="password")
    st.markdown("Upload a CSV/XLSX or paste lines (title,artist,year).")
    col1, col2 = st.columns(2)
    with col1:
        uploaded = st.file_uploader("Drop file here", type=["csv","xls","xlsx"])
    with col2:
        manual = st.text_area(
            "…or paste lines like `Bohemian Rhapsody, Queen, 1975`",
            height=150
        )
    max_tags = st.slider("Max tags per line", 5, 20, value=DEFAULT_MAX_TAGS)
    if st.button("Build Tags", disabled=not (token and (uploaded or manual.strip()))):
        # ingest
        try:
            df = read_uploaded_file(uploaded) if uploaded else read_manual_paste(manual)
        except Exception as e:
            st.error(str(e))
            return

        # process
        out_rows = []
        progress = st.progress(0.0)
        total = len(df)
        for i, row in df.iterrows():
            title, artist, year = row["title"], row["artist"], row["year"]
            label = f"{title} - {artist}".strip(" -")
            try:
                results = discogs_search(token, title, artist, year)
                best    = choose_best(results, title, artist)
                if best:
                    rel  = get_release(token, best["id"])
                    tags = build_tag_list(rel, max_tags)
                else:
                    tags = ["NO_MATCH"]
            except Exception as e:
                tags = [f"ERROR: {e}"]
            out_rows.append({"input_title": label, "udio_tags": ", ".join(tags)})
            progress.progress((i+1)/total)
            time.sleep(SLEEP_BETWEEN)

        df_out = pd.DataFrame(out_rows)
        st.success("Done.")
        st.dataframe(df_out, use_container_width=True)
        st.download_button("Download CSV", df_out.to_csv(index=False), "prompts.csv")
        st.markdown("### Copy individual tag lines")
        for _, r in df_out.iterrows():
            st.code(r["udio_tags"])
