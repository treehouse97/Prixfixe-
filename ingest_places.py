
import sqlite3
from backend.scraper.places_api import find_restaurants
from backend.scraper.scraper import fetch_website_text, detect_prix_fixe
from backend.ai_assist.ai_analyze import ai_analyze_text
from config.settings import DEFAULT_LOCATION, SEARCH_RADIUS_METERS

def ingest_and_scrape():
    print("Connecting to database...")
    conn = sqlite3.connect('data/prix_fixe.db')
    cursor = conn.cursor()

    print("Creating tables if not exist...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS restaurants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        address TEXT,
        website TEXT,
        scraped INTEGER DEFAULT 0,
        has_prix_fixe INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS prix_fixe_menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        restaurant_id INTEGER,
        price REAL,
        description TEXT,
        menu_link TEXT,
        FOREIGN KEY (restaurant_id) REFERENCES restaurants(id)
    )
    """)

    print("Fetching restaurant list...")
    results = find_restaurants(location=DEFAULT_LOCATION, radius=SEARCH_RADIUS_METERS)
    for r in results:
        name = r['name']
        address = r.get('vicinity', '')
        website = r.get('website', '')

        cursor.execute("INSERT INTO restaurants (name, address, website) VALUES (?, ?, ?)", (name, address, website))

    print("Running scraper and AI fallback...")
    cursor.execute("SELECT id, website FROM restaurants WHERE scraped = 0")
    rows = cursor.fetchall()

    for restaurant_id, website in rows:
        if not website:
            continue

        print(f"Scraping {website}...")
        text = fetch_website_text(website)
        found = detect_prix_fixe(text)

        if not found:
            result = ai_analyze_text(text)
            found = result['has_prix_fixe']

        if found:
            cursor.execute("UPDATE restaurants SET has_prix_fixe = 1 WHERE id = ?", (restaurant_id,))
            cursor.execute("INSERT INTO prix_fixe_menus (restaurant_id, price, description, menu_link) VALUES (?, ?, ?, ?)",
                           (restaurant_id, 0.0, 'Prix fixe menu found (details TBD)', website))

        cursor.execute("UPDATE restaurants SET scraped = 1 WHERE id = ?", (restaurant_id,))

    conn.commit()
    conn.close()
    print("Done.")
