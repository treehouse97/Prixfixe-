import json, os, sqlite3, tempfile, time, uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import streamlit as st
from streamlit_lottie import st_lottie

# ── optional folium integration ──────────────────────────────────────────────
try:
    import folium
    from streamlit_folium import st_folium
    MAP_BACKEND = "folium"
except ModuleNotFoundError:
    MAP_BACKEND = "st_map"           # graceful fallback

from scraper    import fetch_website_text, detect_prix_fixe_detailed, PATTERNS
from places_api import text_search_restaurants
from settings   import GOOGLE_API_KEY

# ─── per‑session SQLite -------------------------------------------------------
if "db_file" not in st.session_state:
    st.session_state["db_file"]   = os.path.join(tempfile.gettempdir(), f"fixe_{uuid.uuid4().hex}.db")
    st.session_state["searched"]  = False
    st.session_state["favorites"] = set()

DB_FILE     = st.session_state["db_file"]
LABEL_ORDER = list(PATTERNS.keys())
ACCENT      = "#e74c3c"

SCHEMA = """
CREATE TABLE IF NOT EXISTS restaurants(
 id INTEGER PRIMARY KEY,
 name TEXT,address TEXT,website TEXT,
 label TEXT,raw_text TEXT,location TEXT,
 rating REAL,price_level INTEGER,open_now INTEGER,
 lat REAL,lng REAL,photo_ref TEXT,
 UNIQUE(name,address,location))
"""
def init_db(): sqlite3.connect(DB_FILE).executescript(SCHEMA)
init_db()

# ─── helpers ------------------------------------------------------------------
def store_rows(rows):
    sqlite3.connect(DB_FILE).executemany(
        "INSERT OR IGNORE INTO restaurants VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
def fetch_rows(loc): return sqlite3.connect(DB_FILE).execute(
        "SELECT * FROM restaurants WHERE location=?", (loc,)).fetchall()

def load_lottie(p): return json.load(open(p))
def rating(r): return f"{r:.1f}/5" if r else ""
def textfrag(url,label): return url + "#:~:text=" + quote(label)

def build_card(r):
    (_id,n,a,w,l,_t,_loc,rat,pr,open,lat,lng,photo)=r
    photo_tag = f'<img src="https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photo_reference={photo}&key={GOOGLE_API_KEY}">' if photo else ""
    heart = "❤️" if _id in st.session_state["favorites"] else "🤍"
    return f"""
<div class="card" onclick="fetch('/?fav={_id}')">
 {photo_tag}
 <div class="body">
  <div class="row"><span>{heart}</span><span class="badge">{l}</span></div>
  <div class="title">{n}</div>
  <div class="sub">{a}</div>
  <div class="meta">{rating(rat)} {"$"*pr if pr else ""} {"🟢" if open else ""}</div>
  <a href="{textfrag(w,l)}" target="_blank">Visit Site</a>
 </div></div>""",(lat,lng,n,l)

def label_rank(lbl): 
    try:return LABEL_ORDER.index(lbl.lower())
    except ValueError:return len(LABEL_ORDER)

def prioritize(lst):
    kws={"bistro","brasserie","trattoria","tavern","grill","prix fixe","pre fixe","ristorante"}
    return sorted(lst,key=lambda p:-1 if any(k in p["name"].lower() for k in kws) else 0)

# ─── UI & CSS -----------------------------------------------------------------
st.set_page_config("The Fixe","🍽",layout="wide")
base=st.get_option("theme.base")
TEXT="#111" if base=="light" else "#eee"
CARD_BG="#fff" if base=="light" else "#1e1e1e"
st.markdown(f"""
<style>
.hero{{height:220px;background:#000;margin-bottom:1rem;position:relative;border-radius:12px;overflow:hidden}}
.hero video{{width:100%;height:100%;object-fit:cover;opacity:.35}}
.hero h1{{position:absolute;bottom:20px;left:40px;font-size:2.2rem;color:#fff}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:24px}}
.card{{background:{CARD_BG};border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,.12);cursor:pointer}}
.card img{{width:100%;height:170px;object-fit:cover}}
.body{{padding:12px 16px;color:{TEXT}}}
.title{{font-size:1.05rem;font-weight:600;margin:2px 0}}
.sub{{color:#666;font-size:.9rem}}
.meta{{color:#888;font-size:.8rem}}
.badge{{background:{ACCENT};color:#fff;border-radius:4px;padding:2px 6px;font-size:.7rem;margin-left:.4rem}}
.row{{display:flex;gap:4px;align-items:center}}
a{{color:{ACCENT};text-decoration:none;font-size:.9rem}}
a:hover{{text-decoration:underline}}
</style>
""",unsafe_allow_html=True)

st.markdown(
    """<div class="hero"><video autoplay muted loop>
         <source src="https://cdn.coverr.co/videos/coverr-chef-cooking-7234/1080p.mp4" type="video/mp4">
       </video><h1>Find Prix‑Fixe &amp; Tasting Menus Near You</h1></div>""",
    unsafe_allow_html=True)

# ─── controls -----------------------------------------------------------------
c1,c2,c3,c4=st.columns(4)
location   = c1.text_input("📍 Location","Islip, NY")
min_rating = c2.slider("⭐ Min Rating",0.0,5.0,0.0,0.5)
open_only  = c3.checkbox("Open Now Only")
price_sel  = c4.selectbox("💲 Price",["Any","$","$$","$$$","$$$$"])

# ─── search -------------------------------------------------------------------
def run_search():
    st.info("Searching…")
    data = text_search_restaurants(location)
    rows=[]
    for p in prioritize([x for x in data if x["website"]]):
        if p["rating"] and p["rating"]<min_rating:continue
        if open_only and p["open_now"] is False: continue
        if price_sel!="Any" and p["price_level"]!=len(price_sel): continue
        txt=fetch_website_text(p["website"])
        ok,lbl=detect_prix_fixe_detailed(txt)
        if ok:
            rows.append((None,p["name"],p["address"],p["website"],lbl,txt,
                         location,p["rating"],p["price_level"],
                         int(p["open_now"]) if p["open_now"] is not None else None,
                         p["lat"],p["lng"],p["photo_ref"]))
    init_db(); store_rows(rows)
    st.session_state["searched"]=True

if st.button("Search"): run_search()

# ─── results ------------------------------------------------------------------
if st.session_state["searched"]:
    recs=fetch_rows(location)
    if not recs: st.warning("No menus match current filters.")
    else:
        # map
        if MAP_BACKEND=="folium":
            m=folium.Map(location=[recs[0][10],recs[0][11]],zoom_start=12)
            for r in recs: folium.Marker([r[10],r[11]],tooltip=r[1]).add_to(m)
            st_folium(m,height=280)
        else:
            st.map([{"lat":r[10],"lon":r[11]} for r in recs])

        # cards
        st.markdown('<div class="grid">',unsafe_allow_html=True)
        grouped={}
        for r in recs: grouped.setdefault(r[4].lower(),[]).append(r)
        for lbl in sorted(grouped,key=label_rank):
            st.markdown(f"<h3>{lbl.title()}</h3>",unsafe_allow_html=True)
            for r in grouped[lbl]:
                html,_=build_card(r)
                st.markdown(html,unsafe_allow_html=True)
        st.markdown('</div>',unsafe_allow_html=True)

        # favorites sidebar
        if st.session_state["favorites"]:
            with st.sidebar:
                st.subheader("Favorites")
                for fid in st.session_state["favorites"]:
                    row=next((r for r in recs if r[0]==fid),None)
                    if row: st.markdown(f"• {row[1]}")

# ─── handle ♥ clicks ----------------------------------------------------------
import urllib.parse, os
if (qs:=os.environ.get("QUERY_STRING")):
    fav=urllib.parse.parse_qs(qs).get("fav",[None])[0]
    if fav:
        fid=int(fav); favs=st.session_state["favorites"]
        favs.remove(fid) if fid in favs else favs.add(fid)
        st.experimental_rerun()

# ─── missing‑package hint -----------------------------------------------------
if MAP_BACKEND=="st_map":
    st.warning(
        "Install **streamlit‑folium** for the interactive map:\n\n"
        "`pip install streamlit-folium`", icon="💡"
    )