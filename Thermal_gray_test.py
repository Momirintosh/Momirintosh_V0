import usb.core
import usb.util
import time
import os
from PIL import Image, ImageEnhance  # Added ImageEnhance
from escpos.printer import Usb

# --- Configuration ---
TEST_IMAGE = "QR_CODE_small.bmp"
VENDOR_ID = 0x28e9
PRODUCT_ID = 0x0289

# 1. KICK THE KERNEL
dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
if dev and dev.is_kernel_driver_active(0):
    try:
        dev.detach_kernel_driver(0)
        print("Kernel driver detached.")
    except Exception as e:
        print(f"Kernel note: {e}")

# 2. RUN THE PRINT JOB
try:
    if not os.path.exists(TEST_IMAGE):
        raise FileNotFoundError(f"Image not found at {TEST_IMAGE}")

    # --- IMAGE PRE-PROCESSING FOR GRAY ---
    raw_img = Image.open(TEST_IMAGE).convert("L")
    
    # Increase brightness to "thin out" the blacks (1.0 is original, 2.0 is very bright)
    enhancer = ImageEnhance.Brightness(raw_img)
    bright_img = enhancer.enhance(1.6) 
    
    # Apply the high-detail dithering
    img = bright_img.convert("1", dither=Image.FLOYDSTEINBERG)
    
    # Connect using your confirmed 0x03 endpoint
    p = Usb(VENDOR_ID, PRODUCT_ID, timeout=0, in_ep=0x81, out_ep=0x03)
    
    # Keeping your requested chunking and timing
    SLICE_HEIGHT = 10
    width, height = img.size

    print(f"Starting chunked dithered print (Endpoint 0x03)...")

    for y in range(0, height, SLICE_HEIGHT):
        box = (0, y, width, min(y + SLICE_HEIGHT, height))
        chunk = img.crop(box)
        
        p.image(chunk)
        print(f"Chunk at y={y} sent")
        
        # Keeping your requested 0.15s breather
        time.sleep(0.15)

    p.text("\n" * 3)
    print("Print job successful!")

except Exception as e:
    print(f"An error occurred: {e}")
