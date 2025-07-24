# Discogs → Udio Tag Builder

A lightweight Streamlit app that:
- Takes a CSV of `title, artist, year`
- Fetches Discogs “styles / genres / year / format / label” metadata
- Outputs comma-delimited Udio prompt tags

## Usage

1. Obtain a Discogs token (Discogs ▶ Settings ▶ Developers ▶ Generate token)  
2. Upload a CSV (`title,artist,year`) or paste one track per line  
3. Click **Build tags**  
4. Copy the generated lines or download `prompts.csv`

## Local setup

```bash
conda create -n discogs_tags python=3.11 -y
conda activate discogs_tags
pip install -r requirements.txt
streamlit run app.py
