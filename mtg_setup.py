import json
import sqlite3

# Load the JSON data
with open('AtomicCards.json', 'r') as f:
    full_data = json.load(f)
    cards = full_data['data']

# Connect to (or create) the SQLite database
conn = sqlite3.connect('mtg_atomic.db')
cursor = conn.cursor()

# Create a simple table
cursor.execute('''CREATE TABLE IF NOT EXISTS cards 
                  (name TEXT, manaValue TEXT, type TEXT, text TEXT)''')

# Insert the data
for card_name, card_data in cards.items():
    # Atomic data is an array (to handle different faces/versions)
    # We'll grab the first entry for simplicity
    c = card_data[0]
    cursor.execute("INSERT INTO cards VALUES (?, ?, ?, ?)",
                   (c.get('name'), c.get('manaValue'), c.get('type'), c.get('text')))

conn.commit()
conn.close()
print("Database 'mtg_atomic.db' created successfully!")
