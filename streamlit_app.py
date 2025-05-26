import json, os, sqlite3, tempfile, time, uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import streamlit as st
from streamlit_lottie import st_lottie
from streamlit_folium import st_folium
import folium

from scraper     import fetch_website_text, detect_prix_fixe_detailed, PATTERNS
from places_api  import text_search_restaurants
from settings    import GOOGLE_API_KEY

# ── session‑unique DB so users never see others' data ─────────────────────────
if "db_file" not in st.session_state:
    st.session_state["db_file"]   = os.path.join(tempfile.gettempdir(), f"fixe_{uuid.uuid4().hex}.db")
    st.session_state["searched"]  = False
    st.session_state["favorites"] = set()

DB_FILE      = st.session_state["db_file"]
LABEL_ORDER  = list(PATTERNS.keys())
ACCENT_BASE  = "#e74c3c"

# ── SQLite helpers ────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE restaurants(
 id INTEGER PRIMARY KEY,
 name TEXT,address TEXT,website TEXT,
 label TEXT,raw_text TEXT,location TEXT,
 rating REAL,price_level INTEGER,open_now INTEGER,
 lat REAL,lng REAL,photo_ref TEXT,
 UNIQUE(name,address,location))
"""
def init_db():
    sqlite3.connect(DB_FILE).executescript("DROP TABLE IF EXISTS restaurants;" + SCHEMA)

def store_rows(rows):
    sqlite3.connect(DB_FILE).executemany(
        "INSERT OR IGNORE INTO restaurants VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?)", rows
    )

def fetch_rows(loc):
    cur = sqlite3.connect(DB_FILE).cursor()
    cur.execute("SELECT * FROM restaurants WHERE location=?", (loc,))
    return cur.fetchall()

# ensure DB
if not os.path.exists(DB_FILE):
    init_db()

# ── little helpers ────────────────────────────────────────────────────────────
def load_lottie(path:str):
    with open(path) as f:
        return json.load(f)

def highlight_link(url:str,label:str):
    frag = url + "#:~:text=" + quote(label)
    return frag

def rating_str(r):
    return f"{r:.1f}/5" if r else ""

def build_card(row):
    (
        _id, name, addr, web, lbl, _txt, loc, rating, price, open_now,
        lat, lng, photo
    ) = row
    stars   = rating_str(rating)
    dollar  = "$"*price if price else ""
    open_txt= "🟢 Open" if open_now else "🔴 Closed" if open_now is not None else ""
    fav_on  = "❤️" if _id in st.session_state["favorites"] else "🤍"

    photo_tag = (f'<img loading="lazy" src="https://maps.googleapis.com/maps/api/place/photo?'
                 f'maxwidth=400&photo_reference={photo}&key={GOOGLE_API_KEY}">' if photo else "")

    button_html = (
        f'<button onclick="fetch(\'/?fav={_id}\')" '
        f'style="background:none;border:none;font-size:1.2rem;cursor:pointer">{fav_on}</button>'
    )
    return f"""
    <div class="card">
      {photo_tag}
      <div class="body">
        <div class="row">{button_html}<span class="badge">{lbl}</span></div>
        <div class="title">{name}</div>
        <div class="sub">{addr}</div>
        <div class="meta">{stars} {dollar} {open_txt}</div>
        <a href="{highlight_link(web,lbl)}" target="_blank">Visit Site</a>
      </div>
    </div>""", (lat,lng,name,lbl)

def label_rank(lbl): 
    return LABEL_ORDER.index(lbl) if lbl in LABEL_ORDER else len(LABEL_ORDER)

# ── page config & CSS ─────────────────────────────────────────────────────────
st.set_page_config("The Fixe", "🍽", layout="wide")
st.markdown(
f"""
<style>
html,body{{scroll-behavior:smooth}}
/* hero */
.hero{{position:relative;height:220px;background:#000;border-radius:12px;overflow:hidden;margin-bottom:1.25rem}}
.hero video{{position:absolute;top:0;left:0;width:100%;min-height:100%;object-fit:cover;opacity:.35}}
.hero h1{{position:relative;padding:80px 40px;color:#fff;font-size:2.2rem}}
/* cards */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:24px}}
.card{{background:#fff;border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,.12);display:flex;flex-direction:column}}
.card img{{width:100%;height:170px;object-fit:cover}}
.body{{padding:12px 16px;display:flex;flex-direction:column;gap:4px;font-size:.9rem}}
.title{{font-size:1.05rem;font-weight:600;color:#111;margin:2px 0}}
.sub{{color:#555}}
.meta{{font-size:.8rem;color:#777}}
.badge{{background:{ACCENT_BASE};color:#fff;padding:2px 6px;border-radius:4px;font-size:.7rem;margin-left:.4rem}}
.row{{display:flex;align-items:center;gap:4px}}
a{{text-decoration:none;color:{ACCENT_BASE};font-weight:600;font-size:.9rem}}
a:hover{{text-decoration:underline}}
button:focus{{outline:none}}
</style>
""",
unsafe_allow_html=True)

# ── hero banner ───────────────────────────────────────────────────────────────
with st.container():
    st.markdown(
        """<div class="hero">
              <video autoplay muted loop>
                <source src="https://cdn.coverr.co/videos/coverr-chef-cooking-7234/1080p.mp4" type="video/mp4">
              </video><h1>Find Prix‑Fixe &amp; Tasting Menus Near You</h1></div>""",
        unsafe_allow_html=True,
    )

# ── search controls ───────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
with col1:
    location = st.text_input("📍 Location", "Islip, NY")
with col2:
    min_rating = st.slider("⭐ Min Rating", 0.0, 5.0, 0.0, 0.5)
with col3:
    open_now = st.checkbox("Open Now Only")
with col4:
    price_level = st.selectbox("💲 Price", ["Any", "$", "$$", "$$$", "$$$$"])

# ── search action ─────────────────────────────────────────────────────────────
def run_search(expand=False):
    ph = st.empty(); ph.info("Fetching places...")
    raw = text_search_restaurants(location)
    rows, map_pts = [], []

    for p in raw:
        # filters
        if p["rating"] and p["rating"] < min_rating:          continue
        if open_now and p["open_now"] is False:               continue
        if price_level!="Any" and p["price_level"]!=len(price_level): continue

        text = fetch_website_text(p["website"])
        matched, lbl = detect_prix_fixe_detailed(text)
        if not matched: continue

        rows.append(
            (
                None,
                p["name"],
                p["address"],
                p["website"],
                lbl,
                text,
                location,
                p["rating"],
                p["price_level"],
                int(p["open_now"]) if p["open_now"] is not None else None,
                p["lat"],
                p["lng"],
                p["photo_ref"],
            )
        )
    store_rows(rows)
    st.session_state["searched"] = True
    ph.empty()

if st.button("Search"):
    init_db()
    run_search()

# ── results (cards + map) ─────────────────────────────────────────────────────
if st.session_state["searched"]:
    cards = fetch_rows(location)
    if not cards:
        st.warning("No prix‑fixe menus found with current filters.")
    else:
        # group & sort
        groups = {}
        for r in cards: groups.setdefault(r[4].lower(), []).append(r)
        groups = dict(sorted(groups.items(), key=lambda x: label_rank(x[0])))

        # map
        m = folium.Map(location=[cards[0][10], cards[0][11]], zoom_start=12)
        for _,_,_,_,lbl,_,_,_,_,_,lat,lng,_ in cards:
            folium.Marker([lat,lng], tooltip=lbl).add_to(m)
        st_folium(m, height=280)

        # cards
        st.markdown('<div class="grid">', unsafe_allow_html=True)
        for lbl, items in groups.items():
            st.markdown(f'<h3>{lbl.title()}</h3>', unsafe_allow_html=True)
            for r in items:
                html,_ = build_card(r)
                st.markdown(html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # favorites sidebar
        if st.session_state["favorites"]:
            with st.sidebar:
                st.subheader("Favorites")
                for fid in st.session_state["favorites"]:
                    row = next((r for r in cards if r[0]==fid), None)
                    if row: st.markdown(f"• {row[1]}")

# ── handle '♥' clicks (cheap RPC) ─────────────────────────────────────────────
import urllib.parse, os
if "QUERY_STRING" in os.environ:
    qs = urllib.parse.parse_qs(os.environ["QUERY_STRING"])
    fav = qs.get("fav", [None])[0]
    if fav:
        fid = int(fav)
        favs = st.session_state["favorites"]
        favs.remove(fid) if fid in favs else favs.add(fid)
        st.experimental_rerun()