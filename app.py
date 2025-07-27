import io
import re
import time
import requests
import pandas as pd
import streamlit as st

# ---------------------- CONFIG ----------------------
BASE = "https://api.discogs.com"
UA = {"User-Agent": "DiscogsUdioTagger/0.1 (contact: you@example.com)"}
DEFAULT_MAX_TAGS = 12
SLEEP_BETWEEN = 0.6  # seconds, to respect Discogs rate limits
# ----------------------------------------------------

# ---------------------- HELPERS ----------------------
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
    seen = set(); out = []
    for t in cleaned:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def discogs_search(token, title, artist="", year=""):
    params = {
        "type": "release",
        "per_page": 5,
        "token": token,
        "q": f"{title} {artist}".strip()
    }
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
    if ttl.startswith(title_low):
        score += 3
    if artist_low and artist_low in ttl:
        score += 2
    score += int(r.get("community", {}).get("have", 0)) // 100
    return score

def choose_best(results, title, artist):
    if not results:
        return None
    t, a = title.lower(), artist.lower()
    return sorted(results, key=lambda r: score_result(r, t, a), reverse=True)[0]

def build_tag_list(rel_json, max_tags):
    styles  = rel_json.get("styles", []) or []
    genres  = rel_json.get("genres", []) or []
    year    = str(rel_json.get("year")) if rel_json.get("year") else ""
    country = rel_json.get("country", "")
    formats = [f.get("name","") for f in rel_json.get("formats", [])]
    labels  = [l.get("name","") for l in rel_json.get("labels", [])]

    tokens = []
    tokens += styles
    if len(tokens) < max_tags:
        tokens += genres
    if year:
        tokens.append(year)
    if country:
        tokens.append(country)
    tokens += formats
    tokens += labels

    tokens = clean_tokens(tokens)
    return tokens[:max_tags]

def read_uploaded_file(uploaded_file):
    name = uploaded_file.name.lower()
    try:
        if name.endswith((".xls", ".xlsx")):
            df = pd.read_excel(uploaded_file, dtype=str).fillna("")
        else:
            raw = uploaded_file.read()
            uploaded_file.seek(0)
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
    df = pd.DataFrame(rows, columns=["title","artist","year"]).fillna("")
    return df
# ----------------------------------------------------

# ---------------------- UI ----------------------
st.set_page_config(page_title="Discogs → Udio Tag Builder", layout="wide")
st.title("Discogs → Udio Tag Builder")
st.write("Upload a CSV/XLSX with columns: title,artist,year (year optional).")

with st.expander("How to get a Discogs token", expanded=False):
    st.markdown(
        "1. Log in to Discogs\n"
        "2. Go to **Settings → Developers**\n"
        "3. Generate a personal access token\n"
        "4. Paste it below"
    )

discogs_token = st.text_input("Discogs token", type="password")

left, right = st.columns(2)
with left:
    uploaded = st.file_uploader("Drop your CSV/XLSX here", type=["csv","xls","xlsx"])
with right:
    manual = st.text_area(
        "…or paste one track per line: title,artist,year",
        height=150,
        placeholder="Poison,Bell Biv DeVoe,1990\nShow Me Love,Robin S,1993"
    )

st.divider()
max_tags = st.slider("Max tags per line", 5, 20, DEFAULT_MAX_TAGS)
run = st.button("Build tags", disabled=not (discogs_token and (uploaded or manual.strip())))
# ----------------------------------------------------

if run:
    try:
        if uploaded:
            df_in = read_uploaded_file(uploaded)
        else:
            df_in = read_manual_paste(manual)
    except Exception as e:
        st.error(str(e))
        st.stop()

    out_rows = []
    progress = st.progress(0.0)
    status = st.empty()
    total = len(df_in)

    for i, row in df_in.iterrows():
        title  = str(row["title"])
        artist = str(row["artist"])
        year   = str(row["year"])
        label  = f"{title} - {artist}".strip(" -")
        status.text(f"Processing {i+1}/{total}: {label}")

        try:
            results = discogs_search(discogs_token, title, artist, year)
            best    = choose_best(results, title, artist)
            if not best:
                out_rows.append({"input_title": label, "udio_tags": "NO_MATCH"})
            else:
                rel  = get_release(discogs_token, best["id"])
                tags = build_tag_list(rel, max_tags)
                out_rows.append({"input_title": label, "udio_tags": ", ".join(tags)})
        except Exception as e:
            out_rows.append({"input_title": label, "udio_tags": f"ERROR: {e}"})

        progress.progress((i+1)/total)
        time.sleep(SLEEP_BETWEEN)

    df_out = pd.DataFrame(out_rows)
    st.success("Done.")
    st.dataframe(df_out, use_container_width=True)

    st.download_button("Download CSV", df_out.to_csv(index=False), "prompts.csv", "text/csv")
    st.markdown("### Copy individual tag lines")
    for _, r in df_out.iterrows():
        st.code(r["udio_tags"])
