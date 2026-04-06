import sqlite3
import os
import re
import time
import subprocess
import requests

# --- Configuration ---
DB_FILE = 'mtg_atomic.db'
IMAGE_DIR = 'card_images_monochrome'

# Create the folder if it doesn't exist
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

def clean_filename(text):
    """Strip OS illegal characters and braces."""
    if text is None: return ""
    text = str(text).replace('{', '').replace('}', '')
    return re.sub(r'[\\/*?:"<>|]', '_', text)

def download_and_convert(card_name, mana_value):
    """Downloads and saves as '00_CardName.png'."""
    safe_name = clean_filename(card_name)
    
    # Pad Mana Value to 2 digits (e.g., 3.0 -> 03)
    try:
        val = int(float(mana_value)) if mana_value is not None else 0
        padded_mv = str(val).zfill(2)
    except (ValueError, TypeError):
        padded_mv = "00"
    
    output_file = os.path.join(IMAGE_DIR, f"{padded_mv}_{safe_name}.png")

    # Skip if we already have the file
    if os.path.exists(output_file):
        return output_file

    # Scryfall API
    url = f"https://api.scryfall.com/cards/named?exact={card_name}&format=image&version=normal"
    
    try:
        headers = {'User-Agent': 'MTG-Monochrome-Bot/1.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Magick: Resize -> Grayscale -> 1-bit Monochrome
            cmd = [
                'magick', '-', 
                '-resize', '384x', 
                '-colorspace', 'Gray', 
                '-monochrome', 
                output_file
            ]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            process.communicate(input=response.content)
            
            time.sleep(0.1) # 100ms delay for Scryfall
            return output_file
        else:
            print(f"Scryfall skipped {card_name}: {response.status_code}")
    except Exception as e:
        print(f"Error on {card_name}: {e}")
    
    return None

def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ensure image_path column exists in your new DB
    try:
        cursor.execute("ALTER TABLE cards ADD COLUMN image_path TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass 

    print(f"Scanning {DB_FILE} for cards...")
    # Get everything that hasn't been processed
    cursor.execute("SELECT name, manaValue FROM cards WHERE image_path IS NULL OR image_path = ''")
    rows = cursor.fetchall()
    total = len(rows)

    print(f"Found {total} cards to process.")

    for i, row in enumerate(rows):
        name = row['name']
        mv = row['manaValue']
        
        # Download and get the local path
        img_path = download_and_convert(name, mv)
        
        if img_path:
            # Update the DB so we don't do this card again next time
            cursor.execute("UPDATE cards SET image_path = ? WHERE name = ?", (img_path, name))
            
            # Commit every 10 cards to keep things moving without hitting the disk too hard
            if i % 10 == 0:
                conn.commit()
                print(f"[{i+1}/{total}] Saved: {name}")

    conn.commit()
    conn.close()
    print("All done!")

if __name__ == "__main__":
    main()
