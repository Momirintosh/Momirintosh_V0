import sqlite3
import random
import os
import subprocess
import time
import csv
from datetime import datetime
import usb.core
import usb.util
from PIL import Image, ImageEnhance
from escpos.printer import Usb
from guizero import App, Text, Slider, PushButton, Picture, Box, CheckBox, ListBox, TextBox

# --- Configuration ---
DB_FILE = 'mtg_atomic.db' 
MOMIR_LOG = 'momir_history.csv'
PROXY_LOG = 'proxy_history.csv'
DEFAULT_BACK = 'default_back.png'
ART_REGION = '86x45+25%+59%'

# Printer Hardware Config
VENDOR_ID = 0x28e9
PRODUCT_ID = 0x0289
OUT_EP = 0x03 

class Momirintosh:
    def __init__(self, app):
        self.app = app
        self.app.title = "Momirintosh"
        self.app.set_full_screen()
        self.app.bg = "#2e0854"
        
        self.selected_card_name = ""
        self.original_path = ""
        self.momir_history = [] 

        self.app.when_key_pressed = self.handle_keys

        # --- NAVIGATION ---
        self.nav_bar = Box(self.app, width="fill", align="top")
        self.nav_bar.bg = "#1a0430"
        self.btn_exit = PushButton(self.nav_bar, text="X", command=self.app.destroy, align="left", width=2)
        self.btn_exit.bg = "#d3d3d3"; self.btn_exit.text_color = "#333333"
        self.btn_tab_momir = PushButton(self.nav_bar, text="MOMIR", command=self.show_momir, align="left", width=12)
        self.btn_tab_proxy = PushButton(self.nav_bar, text="PROXY", command=self.show_proxy, align="left", width=12)
        
        for btn in [self.btn_tab_momir, self.btn_tab_proxy]:
            btn.bg = "#4b0082"; btn.text_color = "white"; btn.font = "Courier"

        self.momir_container = Box(self.app, width=800, height=440)
        self.proxy_container = Box(self.app, width=800, height=440)
        self.proxy_container.hide()

        self.setup_momir_ui()
        self.setup_proxy_ui()
        self.show_momir()

    def show_momir(self):
        self.proxy_container.hide(); self.momir_container.show()
        self.btn_tab_momir.bg = "#e0b0ff"; self.btn_tab_momir.text_color = "black"
        self.btn_tab_proxy.bg = "#4b0082"; self.btn_tab_proxy.text_color = "white"

    def show_proxy(self):
        self.momir_container.hide(); self.proxy_container.show()
        self.btn_tab_proxy.bg = "#e0b0ff"; self.btn_tab_proxy.text_color = "black"
        self.btn_tab_momir.bg = "#4b0082"; self.btn_tab_momir.text_color = "white"

    # --- PRINT AREA WITH LOGGING AND RESOURCE FIXES ---
    def print_card(self):
        if not self.selected_card_name: return
        
        self.btn_print.text = "PRINTING..."
        self.btn_print.bg = "#ff0000"
        self.btn_print.disable()
        self.app.update()
        
        dev = None
        try:
            # 1. USB INITIALIZATION & KERNEL KICK
            dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
            if dev is None:
                print("Printer not found.")
                return

            dev.reset() 
            time.sleep(0.5) 

            if dev.is_kernel_driver_active(0):
                try:
                    dev.detach_kernel_driver(0)
                    print("Kernel driver detached.")
                except Exception as e:
                    print(f"Kernel note: {e}")
            
            # 2. IMAGE PRE-PROCESSING
            active_pic = self.card_image if self.momir_container.visible else self.proxy_image
            raw_img = Image.open(active_pic.value).convert("L")
            
            enhancer = ImageEnhance.Brightness(raw_img)
            bright_img = enhancer.enhance(1.6) 
            img = bright_img.convert("1", dither=Image.FLOYDSTEINBERG)
            
            # 3. PRINT LOOP WITH STATUS LOGGING
            p = Usb(VENDOR_ID, PRODUCT_ID, timeout=0, in_ep=0x81, out_ep=0x03)
            
            SLICE_HEIGHT = 40
            width, height = img.size
            print(f"Starting chunked print for: {self.selected_card_name}")

            for y in range(0, height, SLICE_HEIGHT):
                box = (0, y, width, min(y + SLICE_HEIGHT, height))
                chunk = img.crop(box)
                p.image(chunk)
                
                # Progress logging to console
                print(f"Chunk at y={y} sent")
                
                time.sleep(0.15) 
                self.app.update()

            p.text("\n" * 3)
            print("Print job successful!") # Successful print note
            
            # 4. CLEANUP
            p.close() 
            usb.util.dispose_resources(dev)

            # Log to CSV
            log_file = MOMIR_LOG if self.momir_container.visible else PROXY_LOG
            with open(log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), self.selected_card_name])

        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            if dev:
                try: dev.attach_kernel_driver(0)
                except: pass
            self.reset_print_button()

    def reset_print_button(self):
        self.btn_print.text = "PRINT CARD"
        self.btn_print.bg = "white"
        self.btn_print.enable()

    # --- UI SETUP ---
    def setup_momir_ui(self):
        content_box = Box(self.momir_container, layout="grid", width=800, height=440)
        col_left = Box(content_box, grid=[0, 0], width=360, height=440, align="left")
        
        cmc_box = Box(col_left, layout="grid", align="top")
        self.btn_down = PushButton(cmc_box, text="-", command=self.cmc_down, grid=[0,0], width=4, height=2)
        self.cmc_display = Text(cmc_box, text="00", size=70, font="Courier", color="#e0b0ff", grid=[1,0])
        self.btn_up = PushButton(cmc_box, text="+", command=self.cmc_up, grid=[2,0], width=4, height=2)
        self.slider = Slider(col_left, start=0, end=16, width=300, command=self.update_cmc)
        
        self.btn_roll = PushButton(col_left, text="ROLL", command=self.random_print, width=20, height=2)
        self.btn_roll.bg = "white"

        self.btn_clear_hist = PushButton(col_left, text="CLEAR HISTORY", command=self.clear_momir_history, width=20)
        self.btn_clear_hist.bg = "#d3d3d3"

        self.history_box = Box(col_left, width="fill")
        self.history_buttons = []

        col_right = Box(content_box, grid=[1, 0], width=440, height=440)
        self.card_name_text = Text(col_right, text="---", size=14, color="white")
        self.card_image = Picture(col_right, image=DEFAULT_BACK, width=1, height=1)
        
        action_box = Box(col_right, width="fill", layout="grid")
        self.check_invert = CheckBox(action_box, text="Invert Art", grid=[0,0], 
                                     command=lambda: self.refresh_image_logic(self.card_image, self.check_invert))
        self.check_invert.text_color="white"
        self.btn_print = PushButton(action_box, text="PRINT CARD", command=self.print_card, grid=[1,0])
        self.btn_print.bg = "white"; self.btn_print.disable()

    def setup_proxy_ui(self):
        proxy_grid = Box(self.proxy_container, layout="grid", width=800, height=440)
        col_left = Box(proxy_grid, grid=[0,0], width=360, height=440)
        Text(col_left, text="Manual Search", size=18, color="#e0b0ff")
        search_box = Box(col_left, width="fill", layout="grid")
        self.proxy_input = TextBox(search_box, grid=[0,0], width=20); self.proxy_input.bg = "white"
        self.proxy_input.tk.bind('<Return>', lambda e: self.add_local_proxy())
        PushButton(search_box, text="ADD", grid=[1,0], command=self.add_local_proxy)
        self.proxy_list = ListBox(col_left, items=[], width="fill", height=200, command=self.update_proxy_preview)
        self.proxy_list.bg = "#1a0430"; self.proxy_list.text_color = "white"
        PushButton(col_left, text="REMOVE SELECTED", command=self.remove_selected_proxy, width="fill")

        col_right = Box(proxy_grid, grid=[1,0], width=440, height=440)
        self.proxy_name_text = Text(col_right, text="---", size=14, color="white")
        self.proxy_image = Picture(col_right, image=DEFAULT_BACK, width=260, height=360)
        p_action_box = Box(col_right, width="fill", layout="grid")
        self.proxy_invert = CheckBox(p_action_box, text="Invert Art", grid=[0,0], 
                                     command=lambda: self.refresh_image_logic(self.proxy_image, self.proxy_invert))
        self.proxy_invert.text_color = "white"
        self.btn_proxy_print = PushButton(p_action_box, text="PRINT CARD", grid=[1,0], command=self.print_card)
        self.btn_proxy_print.bg = "white"

    # --- LOGIC HELPERS ---
    def clear_momir_history(self):
        self.momir_history.clear()
        for btn in self.history_buttons: btn.destroy()
        self.history_buttons.clear()

    def update_history_display(self, name, path):
        self.momir_history.insert(0, (name, path))
        if len(self.momir_history) > 3: self.momir_history.pop()
        for btn in self.history_buttons: btn.destroy()
        self.history_buttons.clear()
        for h_name, h_path in self.momir_history:
            btn = PushButton(self.history_box, text=h_name, width="fill", command=self.load_historical_card, args=[h_name, h_path])
            btn.bg = "#1a0430"; btn.text_color = "white"
            self.history_buttons.append(btn)

    def load_historical_card(self, name, path):
        self.selected_card_name = name; self.original_path = path
        self.card_name_text.value = name
        self.check_invert.value = 1 if self.check_if_mostly_black(path) else 0
        #self.refresh_image_logic(self.card_image, self.check_invert)
        self.btn_print.enable()

    def get_random_card(self):
        try:
            conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
            cursor = conn.cursor(); val = int(self.slider.value)
            query = "SELECT name, image_path FROM cards WHERE CAST(manaValue AS INTEGER) = ? AND type LIKE '%Creature%' AND image_path IS NOT NULL ORDER BY RANDOM() LIMIT 1"
            cursor.execute(query, (val,)); row = cursor.fetchone(); conn.close()
            if row:
                self.selected_card_name = row['name']; self.original_path = row['image_path']
                #self.card_name_text.value = self.selected_card_name
                self.check_invert.value = 1 if self.check_if_mostly_black(self.original_path) else 0
                self.refresh_image_logic(self.card_image, self.check_invert)
                self.btn_print.enable()
                self.update_history_display(self.selected_card_name, self.original_path)
                self.print_card
        except: pass
    def random_print(self):
        self.get_random_card()
        self.print_card()		

    def add_local_proxy(self):
        name = self.proxy_input.value.strip()
        if not name: return
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM cards WHERE name LIKE ? LIMIT 1", (f'%{name}%',))
        row = cursor.fetchone(); conn.close()
        if row: 
            self.proxy_list.append(row[0]); self.proxy_input.clear()
            self.proxy_list.value = row[0]; self.update_proxy_preview()

    def update_proxy_preview(self):
        name = self.proxy_list.value
        if not name: return
        conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT name, image_path FROM cards WHERE name = ? LIMIT 1", (name,))
        row = cursor.fetchone(); conn.close()
        if row:
            self.selected_card_name = row['name']; self.original_path = row['image_path']
            self.proxy_name_text.value = self.selected_card_name
            self.proxy_invert.value = 1 if self.check_if_mostly_black(self.original_path) else 0
            self.refresh_image_logic(self.proxy_image, self.proxy_invert)

    def remove_selected_proxy(self):
        if self.proxy_list.value: self.proxy_list.remove(self.proxy_list.value)

    def handle_keys(self, event):
        if self.proxy_input.focus: return 
        if event.key == " ": self.get_random_card()
        elif event.tk_event.keysym == "Up": self.cmc_up()
        elif event.tk_event.keysym == "Down": self.cmc_down()

    def cmc_up(self): self.slider.value += 1; self.update_cmc(self.slider.value)
    def cmc_down(self): self.slider.value -= 1; self.update_cmc(self.slider.value)
    def update_cmc(self, value): self.cmc_display.value = str(value).zfill(2)

    def refresh_image_logic(self, target_picture, invert_checkbox):
        if not self.original_path or not os.path.exists(self.original_path): return
        if invert_checkbox.value == 1:
            base = os.path.splitext(self.original_path)[0]
            region_path = f"{base}_inv.png"
            subprocess.run(['magick', self.original_path, '-region', ART_REGION, '-negate', region_path])
            target_picture.value = region_path
        else:
            target_picture.value = self.original_path

    def check_if_mostly_black(self, path):
        try:
            result = subprocess.check_output(['magick', path, '-region', ART_REGION, '-colorspace', 'Gray', '-format', '%[fx:mean]', 'info:'])
            return float(result.decode().strip()) < 0.5
        except: return False

if __name__ == "__main__":
    app = App()
    ui = Momirintosh(app)
    app.display()
