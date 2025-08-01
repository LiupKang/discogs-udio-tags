# File: udio_tools.py

import io
import re
import time
import os
import streamlit as st
import pandas as pd
import requests

DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")
BASE          = "https://api.discogs.com"
UA            = {"User-Agent":"DiscogsUdioTagger/0.1"}
DEFAULT_MAX_TAGS = 12
SLEEP_BETWEEN = 0.6

def clean_tokens(tokens):
    cleaned, seen = [], set()
    for t in tokens:
        t = t.strip().lower()
        if not t: continue
        t = re.sub(r"\s*&\s*", " and ", t)
        t = re.sub(r"[()/]",   " ", t)
        t = re.sub(r"\s+",     " ", t).strip()
        if t not in seen:
            seen.add(t)
            cleaned.append(t)
    return cleaned

def discogs_search(title, artist="", year=""):
    params = {"type":"release","per_page":5,"token":DISCOGS_TOKEN,"q":f"{title} {artist}".strip()}
    if year:
        y = year.rstrip("s")
        if y.isdigit():
            params["year"] = y
    r = requests.get(f"{BASE}/database/search", headers=UA, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("results", [])

def choose_best(results, title, artist):
    if not results: return None
    def score(r):
        s   = 3 if title.lower() and r.get("title","").lower().startswith(title.lower()) else 0
        art = artist.lower()
        if art and art in r.get("title","").lower(): s += 2
        s  += int(r.get("community",{}).get("have",0))//100
        return s
    return max(results, key=score)

def build_tag_list(rel, max_tags):
    styles = rel.get("styles",[]) or []
    genres = rel.get("genres",[]) or []
    year   = str(rel.get("year","")) if rel.get("year") else ""
    country= rel.get("country","")
    fmts   = [f.get("name","") for f in rel.get("formats",[])]
    labs   = [l.get("name","") for l in rel.get("labels",[])]
    tokens = styles + genres
    if year:    tokens.append(year)
    if country: tokens.append(country)
    tokens += fmts + labs
    return clean_tokens(tokens)[:max_tags]

def read_uploaded_file(uploaded):
    raw = uploaded.read(); uploaded.seek(0)
    name= uploaded.name.lower()
    try:
        if name.endswith((".xls",".xlsx")):
            df = pd.read_excel(io.BytesIO(raw), dtype=str).fillna("")
        else:
            df = pd.read_csv(io.BytesIO(raw), dtype=str, sep=None, engine="python", on_bad_lines="skip").fillna("")
    except Exception as e:
        raise ValueError(f"Can't parse file: {e}")
    for c in ("title","artist","year"):
        if c not in df.columns:
            df[c] = ""
    return df[["title","artist","year"]]

def read_manual_paste(text):
    rows=[]
    for line in text.splitlines():
        p=line.split(",",2)
        rows.append((p[0].strip(), p[1].strip() if len(p)>1 else "", p[2].strip() if len(p)>2 else ""))
    return pd.DataFrame(rows, columns=["title","artist","year"]).fillna("")

def run_udio_tag_builder():
    st.header("🎵 Discogs → Udio Tag Builder")
    st.markdown("Upload CSV/XLSX or paste lines (`title,artist,year`).")
    c1,c2=st.columns(2)
    with c1:
        up=st.file_uploader("Drop file", type=["csv","xls","xlsx"])
    with c2:
        ml=st.text_area("…or paste lines", height=150)

    max_tags = st.slider("Max tags per line", 5, 20, value=DEFAULT_MAX_TAGS)
    if not (up or ml.strip()):
        st.info("Provide file or paste lines."); return

    try:
        df = read_uploaded_file(up) if up else read_manual_paste(ml)
    except Exception as e:
        st.error(str(e)); return

    rows, prog=[], st.progress(0.0)
    total = len(df)
    for i,row in df.iterrows():
        t,a,y=row["title"],row["artist"],row["year"]
        label=f"{t} - {a}".strip(" -")
        try:
            res  = discogs_search(t,a,y)
            best = choose_best(res,t,a)
            if best:
                rel = requests.get(f"{BASE}/releases/{best['id']}", headers=UA, params={"token":DISCOGS_TOKEN}).json()
                tags=build_tag_list(rel,max_tags)
            else:
                tags=["NO_MATCH"]
        except Exception as e:
            tags=[f"ERROR: {e}"]

        rows.append({"input_title":label,"udio_tags":", ".join(tags)})
        prog.progress((i+1)/total)
        time.sleep(SLEEP_BETWEEN)

    out=pd.DataFrame(rows)
    st.success("Done.")
    st.dataframe(out,use_container_width=True)
    st.download_button("Download CSV", out.to_csv(index=False),"prompts.csv")
    st.markdown("### Copy tag lines")
    for _,r in out.iterrows():
        st.code(r["udio_tags"])
