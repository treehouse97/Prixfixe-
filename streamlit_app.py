import sqlite3
import streamlit as st

DB_PATH = "prix_fixe.db"

st.title("Prix Fixe Menu Finder")

def load_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, address FROM restaurants WHERE has_prix_fixe = 1")
    rows = cursor.fetchall()
    conn.close()
    return rows

results = load_data()

if results:
    st.subheader(f"Found {len(results)} restaurants with Prix Fixe menus")
    for name, address in results:
        st.markdown(f"**{name}**  \n{address}")
else:
    st.info("No prix fixe menus found yet. Run the scraper first.")
