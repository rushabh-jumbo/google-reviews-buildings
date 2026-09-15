"""Hand-collected proof-of-concept reviews (pulled via browser, not the blocked
listugcposts endpoint) for a handful of buildings, so we can see real review
text before committing to a full scrape. Rerun-safe (INSERT OR REPLACE)."""
import sqlite3, os
from datetime import datetime, timezone

DB = os.path.join(os.path.dirname(__file__), "reviews.db")
NOW = datetime.now(timezone.utc).isoformat()

# (building_name, author, rating_stars, text, when)
DATA = {
    "Vijaya Springwoods": [
        ("Blessy B Mathew", None, "CONS: Lot of mosquitoes (daily fogging is done, but even then it is bad). A lot of pigeon droppings in between the adjacent house spacings.", "11 months ago"),
        ("Pallabi Roy", None, "Good flats with ventilation. Sunlight on the right side of the building an issue though. While many families stay here, it is actually one of the most accessible to road flats I've come across.", "8 months ago"),
        ("tarun agarwal", None, "I am a tenant and association is the biggest fraud in this apartment. Few of the owners become members of association on rolling basis who stay in the apartment. These owners have large families and they will not allow others.", "2 years ago"),
        ("Abha kumari", None, "They used to leave their 2 dogs in apartment all alone for hours together and they used to cry and bark incessantly. And this consistently happened on weekends.", "8 years ago"),
        ("Nitin Mangesh", None, "Association is highly accommodating, proactive and best. I am a tenant and got just the best place to stay with all amenities around, reach to several places is easy.", "4 years ago"),
        ("Ayas Ghosh", None, "Vijaya springwoods is located near begur road. Major Supermarkets, local grocery store, medical shops are in walkable distance.", "4 years ago"),
        ("dharshana rajendran", None, "Very lovely place with amazing greenery. Very hard to find such place in bangalore.", "7 years ago"),
        ("Divya Rathore", None, "Appartment is very pleasant to go! It's surrounded near the city so everything is near by. The security is quite strict due to the corona which is also a good initiative.", "6 years ago"),
        ("Amit Joshi", None, "Neat and clean society, cleaning staff does their job nicely. Managing committee also take care of society security and other required amenities.", "2 years ago"),
    ],
    "Brigade Lakeview Apartment": [
        ("Rasha Mall", 5, "I'm so impressed with Cureskin! Their products are effective and affordable.", "a year ago"),
        ("Vivek Kumar", None, "Nice lace to live. very peaceful atmosphere.", "8 years ago"),
        ("Dada Khalandar", 5, "Good", "6 years ago"),
        ("manoj ts", 5, "Good apartment", "4 years ago"),
        ("VINAY JAIN", 5, "(no text, 5 stars)", "3 months ago"),
        ("Pawan Mb", 5, "(no text, 5 stars)", "2 years ago"),
        ("Adhil Abdul Majeed", 4, "(no text, 4 stars)", "2 years ago"),
    ],
    "Alps Pleasanton": [
        ("sujeet kumar", None, "Nice Place I am owning a flat here project is fully approved by SBI and HDFC. Flat is accessible by road. Nice community. Apartment has all facilities covered parking swimming pool gym party hall library children park, walkway.", "5 years ago"),
        ("Swati Singh", None, "Good property good design and best part is under budget price with ample amenities. Location is very perfect close to all major IT hubs wipro infy hp Siemens.", "7 years ago"),
        ("Sanjit Kumar Mishra", None, "May be the best project in Neeladri Vihar Electronic City when it comes to value of money. The project is having a valid OC which is very rare in that area. Except the approach road (for which I gave 1 star less) everything is just great.", "7 years ago"),
    ],
    "Celebrity Harmony": [
        ("Vilas Nafde", None, "We have been staying here since last fourteen months and feel like we are here for ages. Very calm and serene surroundings and supportive neighborhood. Pollution free life. Accessibility to market is little issue but with online ordering it's manageable.", "4 years ago"),
        ("Karthik Danthi M", None, "It is a peaceful community with beautiful villas. Close to nature.", "2 years ago"),
        ("suman Vaishnav", None, "Nice place to stay with peace of mind.", "3 years ago"),
    ],
}

def main():
    db = sqlite3.connect(DB)
    total = 0
    for name, reviews in DATA.items():
        row = db.execute("SELECT id FROM buildings WHERE name=?", (name,)).fetchone()
        if not row:
            print(f"SKIP (not found): {name}")
            continue
        bid = row[0]
        for i, (author, rating, text, when) in enumerate(reviews):
            rid = f"{bid}:{i}"
            db.execute(
                "INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?,?,?,?,?)",
                (rid, bid, rating, text, when, "en", author, None, NOW))
            total += 1
    db.commit()
    print(f"inserted/updated {total} reviews")

if __name__ == "__main__":
    main()
