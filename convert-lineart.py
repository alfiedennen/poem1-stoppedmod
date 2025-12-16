"""
Convert lineart images to device-compatible format

Problem: Gemini outputs JPEG data in PNG containers at 1344x784
Device needs: Actual PNG, 510x300, small file size
"""

import os
from PIL import Image

lineart_dir = os.path.join(os.path.dirname(__file__), 'lineart')
output_dir = os.path.join(os.path.dirname(__file__), 'lineart-device')

# Create output directory
os.makedirs(output_dir, exist_ok=True)

# Get all lineart files
files = [f for f in os.listdir(lineart_dir) if f.endswith('_lineart.png')]
files.sort()

print(f"Converting {len(files)} lineart images to device format...")
print("Target: PNG, 510x300, grayscale\n")

success = 0
failed = 0

for i, file in enumerate(files):
    input_path = os.path.join(lineart_dir, file)
    output_path = os.path.join(output_dir, file)

    short_name = file[:50] + "..." if len(file) > 50 else file
    print(f"[{i+1}/{len(files)}] {short_name}", end=" ")

    try:
        img = Image.open(input_path)
        # Convert to grayscale
        img = img.convert('L')
        # Resize to device dimensions
        img = img.resize((510, 300), Image.LANCZOS)
        # Save as proper PNG
        img.save(output_path, 'PNG', optimize=True)

        # Report size
        size_kb = os.path.getsize(output_path) / 1024
        print(f"-> {size_kb:.1f}KB")
        success += 1
    except Exception as e:
        print(f"FAILED: {e}")
        failed += 1

print(f"\n=== Conversion Complete ===")
print(f"Success: {success}/{len(files)}")
print(f"Failed: {failed}/{len(files)}")
print(f"\nOutput directory: {output_dir}")
