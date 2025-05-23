if st.button("Scrape Restaurants in Area"):
    try:
        raw_places = text_search_restaurants(user_location)
        enriched = []
        for place in raw_places:
            name = place.get("name", "")
            address = place.get("vicinity", "")
            website = place.get("website", "")
            if not website:
                continue

            text = fetch_website_text(website)
            matched, label = detect_prix_fixe_detailed(text)

            if matched:
                st.markdown(f"**{name}** - {address}, Detected: {label}")
                enriched.append((name, address, 1))
            else:
                print(f"Skipped {name} — no prix fixe keywords found.")

        store_restaurants(enriched)
        st.success("Restaurants with prix fixe offers saved.")

    except Exception as e:
        st.error(f"Failed to store data: {e}")