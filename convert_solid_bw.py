"""
Convert Dithered Images to Solid Black & White

Applies blur to merge dither dots, then thresholds to get solid B&W regions.
"""

import os
import sys
from pathlib import Path
from PIL import Image, ImageFilter
import numpy as np


def convert_to_solid_bw(image_path, output_path, blur_radius=2, threshold=128):
    """Convert dithered image to solid B&W by blurring then thresholding."""
    img = Image.open(image_path).convert('L')

    # Blur to merge dither dots into solid regions
    blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # Threshold to pure black/white
    pixels = np.array(blurred)
    bw_pixels = (pixels > threshold).astype(np.uint8) * 255

    # Create output
    bw_img = Image.fromarray(bw_pixels, mode='L')
    bw_img = bw_img.convert('1')  # 1-bit for smallest size
    bw_img.save(output_path, 'PNG', optimize=True)

    return os.path.getsize(output_path)


def process_directory(input_dir, output_dir, blur_radius=2, threshold=128):
    """Process all dithered images."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(input_dir.glob('*_dither.png'))
    print(f"Converting {len(images)} images")
    print(f"Blur radius: {blur_radius}, Threshold: {threshold}")
    print(f"Output: {output_dir}\n")

    total_size = 0
    for i, img_path in enumerate(images):
        out_name = img_path.name.replace('_dither', '_solid')
        out_path = output_dir / out_name

        size = convert_to_solid_bw(img_path, out_path, blur_radius, threshold)
        total_size += size

        if (i + 1) % 30 == 0:
            print(f"  {i + 1}/{len(images)}...")

    print(f"\nDone! Total: {total_size/1024/1024:.1f} MB")


if __name__ == '__main__':
    input_dir = sys.argv[1] if len(sys.argv) > 1 else '../croppedimages'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './solid_bw'
    blur = float(sys.argv[3]) if len(sys.argv) > 3 else 2
    thresh = int(sys.argv[4]) if len(sys.argv) > 4 else 128

    process_directory(input_dir, output_dir, blur, thresh)
