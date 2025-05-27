import json, os, sqlite3, tempfile, time, uuid, re
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from streamlit_lottie import st_lottie

from scraper import fetch_website_text, detect_prix_fixe_detailed, PATTERNS
from places_api import text_search_restaurants, place_details          # ← details for reviews
from settings import GOOGLE_API_KEY


# ────────────────── helpers ───────────────────────────────────────────────────
def safe_rerun(): (st.rerun if hasattr(st, "rerun") else st.experimental_rerun)()

def clean_for_sqlite(s: str) -> str:
    """Remove lone surrogate code‑points so SQLite can UTF‑8‑encode."""
    return s.encode("utf-8", "ignore").decode("utf-8", "ignore")

def nice_types(tp: list[str]) -> list[str]:
    """Readable chips from Google types, filtering generic words."""
    ban = {
        "restaurant", "food", "point_of_interest", "establishment",
        "store", "bar", "meal_takeaway", "meal_delivery"
    }
    return [t.replace("_", " ").title() for t in tp if t not in ban][:3]

def first_review(place_id: str) -> str:
    """Return ≤ 100 chars from the first user review or empty string."""
    try:
        res = place_details(place_id)
        rev = (res.get("reviews") or [{}])[0].get("text", "")
        rev = re.sub(r"\s+", " ", rev).strip()
        return (rev[:100] + "…") if len(rev) > 100 else rev
    except Exception:
        return ""

# ────────────────── per‑session database ─────────────────────────────────────
if "db_file" not in st.session_state:
    st.session_state["db_file"] = os.path.join(
        tempfile.gettempdir(), f"prix_fixe_{uuid.uuid4().hex}.db")
    st.session_state.update(searched=False)

DB_FILE = st.session_state["db_file"]
LABEL_ORDER = list(PATTERNS.keys())

SCHEMA = """
CREATE TABLE restaurants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, address TEXT, website TEXT,
    has_prix_fixe INTEGER, label TEXT,
    raw_text TEXT, snippet TEXT, types TEXT,
    location TEXT, rating REAL, photo_ref TEXT,
    UNIQUE(name, address, location)
);
"""

def init_db():
    with sqlite3.connect(DB_FILE) as c:
        c.executescript("DROP TABLE IF EXISTS restaurants;" + SCHEMA)

def ensure_schema():
    if not os.path.exists(DB_FILE): init_db(); return
    try:
        with sqlite3.connect(DB_FILE) as c:
            c.execute("SELECT types FROM restaurants LIMIT 1")
    except sqlite3.OperationalError:   # pre‑types DB
        init_db()

def store_rows(rows):
    with sqlite3.connect(DB_FILE) as c:
        c.executemany("""
            INSERT OR IGNORE INTO restaurants
            (name,address,website,has_prix_fixe,label,raw_text,
             snippet,types,location,rating,photo_ref)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, rows)

def fetch_records(location):
    with sqlite3.connect(DB_FILE) as c:
        return c.execute("""
            SELECT name,address,website,label,snippet,types,rating,photo_ref
            FROM restaurants WHERE has_prix_fixe=1 AND location=?
        """, (location,)).fetchall()

# ────────────────── data acquisition ─────────────────────────────────────────
def prioritize(places):
    hits = {"bistro","brasserie","trattoria","tavern",
            "grill","prix fixe","pre fixe","ristorante"}
    return sorted(
        places,
        key=lambda p: -1 if any(k in p.get("name","").lower() for k in hits) else 0
    )

def process_place(place, loc):
    name, addr   = place["name"], place["vicinity"]
    web          = place.get("website")
    rating       = place.get("rating")
    photo        = place.get("photo_ref")
    p_id         = place.get("place_id")
    g_types      = place.get("types", [])

    # skip duplicates
    with sqlite3.connect(DB_FILE) as c:
        if c.execute("""SELECT 1 FROM restaurants
                        WHERE name=? AND address=? AND location=?""",
                     (name, addr, loc)).fetchone():
            return None

    try:
        text = fetch_website_text(web) if web else ""
        text = clean_for_sqlite(text)
        matched, lbl = detect_prix_fixe_detailed(text)
        if matched:
            snippet = first_review(p_id)
            types_txt = ", ".join(nice_types(g_types))
            return (name,addr,web,1,lbl,text,snippet,types_txt,
                    loc,rating,photo)
    except Exception:
        pass
    return None

# ────────────────── UI helpers ───────────────────────────────────────────────
def format_rating(r): return f"{r:.1f} / 5" if r else ""

def build_card(name,addr,web,lbl,snippet,types_txt,rating,photo):
    chips = "".join(
        f'<span class="chip">{t}</span>'
        for t in (types_txt.split(", ") if types_txt else [])
    )
    photo_tag = (f'<img src="https://maps.googleapis.com/maps/api/place/photo'
                 f'?maxwidth=400&photo_reference={photo}&key={GOOGLE_API_KEY}">'
                 if photo else "")
    snippet_html = f'<p class="snippet">{snippet}</p>' if snippet else ""
    rating_html  = f'<div class="rate">{format_rating(rating)}</div>' if rating else ""
    return f"""
<div class="card">
  {photo_tag}
  <div class="body">
    <span class="badge">{lbl}</span>
    <div class="title">{name}</div>
    {snippet_html}
    <div class="chips">{chips}</div>
    <div class="addr">{addr}</div>
    {rating_html}
    <a href="{web}" target="_blank">Visit&nbsp;Site</a>
  </div>
</div>"""

def label_rank(lbl):
    return LABEL_ORDER.index(lbl.lower()) if lbl.lower() in LABEL_ORDER else 999

# ────────────────── Streamlit page setup ─────────────────────────────────────
st.set_page_config("The Fixe", "🍽", layout="wide")
st.markdown("""
<style>
html,body,[data-testid="stAppViewContainer"]{background:#f8f9fa!important;color:#111!important;}

.stButton>button{background:#212529!important;color:#fff!important;border-radius:4px!important;font-weight:600!important;}
.stButton>button:hover{background:#343a40!important;}

.stTextInput input{background:#fff!important;color:#111!important;border:1px solid #ced4da!important;}

.card{border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,.1);overflow:hidden;background:#fff;margin-bottom:24px}
.card img{width:100%;height:180px;object-fit:cover}
.body{padding:12px 16px}
.title{font-size:1.05rem;font-weight:600;margin-bottom:2px;color:#111;}
.snippet{font-size:.83rem;color:#444;margin:.35rem 0 .5rem}
.addr{font-size:.9rem;color:#555;margin-bottom:6px}
.rate{font-size:.9rem;color:#f39c12;margin-bottom:8px}
.badge{display:inline-block;background:#e74c3c;color:#fff;border-radius:4px;padding:2px 6px;font-size:.75rem;margin-bottom:6px}
.chip{display:inline-block;background:#e1e5ea;color:#111;border-radius:999px;padding:2px 8px;font-size:.72rem;margin-right:4px;margin-bottom:4px}
</style>
""", unsafe_allow_html=True)

# ────────────────── app logic ────────────────────────────────────────────────
ensure_schema()

st.title("The Fixe")
if st.button("Reset Database"):
    init_db(); st.session_state["searched"] = False; safe_rerun()

location = st.text_input("Enter a town, hamlet, or neighborhood", "Islip, NY")

def run_search(limit):
    status, anim = st.empty(), st.empty()
    status.markdown("### Please wait for The Fixe…<br/>(be patient, we’re cooking)",
                    unsafe_allow_html=True)
    load = load_lottie = lambda p: json.load(open(p))
    cook = load_lottie("Animation - 1748132250829.json")
    if cook: st_lottie(cook, height=260, key=f"cook-{time.time()}")

    try:
        raw = text_search_restaurants(location)
        cand = prioritize([p for p in raw if p.get("website")])
        if limit: cand = cand[:limit]
        with ThreadPoolExecutor(max_workers=10) as ex:
            rows = list(ex.map(lambda p: process_place(p, location), cand))
        store_rows([r for r in rows if r])
    except Exception as e:
        st.error(f"Search failed: {e}")

    status.markdown("### The Fixe is in. Scroll below to see the deals.",
                    unsafe_allow_html=True)

if st.button("Search"):
    st.session_state.update(searched=True, expanded=False)
    run_search(limit=25)

if st.session_state.get("searched"):
    records = fetch_records(location)
    if records:
        grouped={}
        for rec in records:
            grouped.setdefault(rec[3].lower(), []).append(rec)
        for lbl in sorted(grouped, key=label_rank):
            st.subheader(lbl.title())
            cols = st.columns(3)
            for i,(name,addr,web,_,snippet,types_txt,rating,photo) in \
                    enumerate(grouped[lbl]):
                with cols[i%3]:
                    st.markdown(build_card(name,addr,web,lbl,snippet,types_txt,
                                           rating,photo), unsafe_allow_html=True)
        if not st.session_state["expanded"]:
            st.markdown("---")
            if st.button("Expand Search"):
                st.session_state["expanded"]=True
                run_search(limit=None)
                safe_rerun()
    else:
        st.info("No prix fixe menus stored yet for this location.")