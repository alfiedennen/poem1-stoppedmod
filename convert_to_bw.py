"""
Convert Living Clock Images to Pure Black & White

Converts grayscale/dithered images to pure 1-bit black and white
using adaptive thresholding for best results across varying images.
"""

import os
import sys
from pathlib import Path
from PIL import Image
import numpy as np

# Threshold methods
THRESHOLD_OTSU = 'otsu'      # Automatic optimal threshold per image
THRESHOLD_FIXED = 'fixed'    # Fixed threshold (e.g., 128)
THRESHOLD_MEAN = 'mean'      # Use image mean as threshold

DEFAULT_METHOD = THRESHOLD_OTSU
FIXED_THRESHOLD = 128


def otsu_threshold(pixels):
    """Calculate Otsu's optimal threshold."""
    hist, _ = np.histogram(pixels.flatten(), bins=256, range=(0, 256))
    total = pixels.size

    sum_total = np.sum(np.arange(256) * hist)
    sum_bg = 0
    weight_bg = 0

    max_variance = 0
    threshold = 0

    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue

        weight_fg = total - weight_bg
        if weight_fg == 0:
            break

        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg

        variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2

        if variance > max_variance:
            max_variance = variance
            threshold = t

    return threshold


def convert_to_bw(image_path, output_path, method=DEFAULT_METHOD):
    """Convert image to pure black and white."""
    img = Image.open(image_path).convert('L')
    pixels = np.array(img)

    # Determine threshold
    if method == THRESHOLD_OTSU:
        threshold = otsu_threshold(pixels)
    elif method == THRESHOLD_MEAN:
        threshold = int(np.mean(pixels))
    else:
        threshold = FIXED_THRESHOLD

    # Apply threshold
    bw_pixels = (pixels > threshold).astype(np.uint8) * 255

    # Create output image
    bw_img = Image.fromarray(bw_pixels, mode='L')

    # Save as 1-bit to minimize file size
    bw_img = bw_img.convert('1')
    bw_img.save(output_path, 'PNG', optimize=True)

    return threshold, os.path.getsize(output_path)


def process_directory(input_dir, output_dir, pattern='*_dither.png', method=DEFAULT_METHOD):
    """Process all images in directory."""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(input_dir.glob(pattern))
    print(f"Found {len(images)} images to convert")
    print(f"Method: {method}")
    print(f"Output: {output_dir}\n")

    results = []
    total_original = 0
    total_converted = 0

    for i, img_path in enumerate(images):
        # Output filename: replace _dither with _bw
        out_name = img_path.name.replace('_dither', '_bw')
        out_path = output_dir / out_name

        original_size = os.path.getsize(img_path)
        total_original += original_size

        try:
            threshold, new_size = convert_to_bw(img_path, out_path, method)
            total_converted += new_size

            reduction = (1 - new_size / original_size) * 100
            results.append({
                'file': out_name,
                'threshold': threshold,
                'original_kb': original_size / 1024,
                'new_kb': new_size / 1024,
                'reduction': reduction
            })

            if (i + 1) % 20 == 0:
                print(f"  Processed {i + 1}/{len(images)}...")

        except Exception as e:
            print(f"  Error processing {img_path.name}: {e}")

    # Summary
    print(f"\n{'='*60}")
    print("CONVERSION SUMMARY")
    print(f"{'='*60}")
    print(f"Images converted: {len(results)}")
    print(f"Original total: {total_original/1024/1024:.1f} MB")
    print(f"Converted total: {total_converted/1024/1024:.1f} MB")
    print(f"Size reduction: {(1 - total_converted/total_original)*100:.1f}%")

    # Threshold distribution
    thresholds = [r['threshold'] for r in results]
    print(f"\nThreshold stats:")
    print(f"  Min: {min(thresholds)}")
    print(f"  Max: {max(thresholds)}")
    print(f"  Avg: {np.mean(thresholds):.0f}")

    return results


if __name__ == '__main__':
    input_dir = sys.argv[1] if len(sys.argv) > 1 else '../croppedimages'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './bw_images'
    method = sys.argv[3] if len(sys.argv) > 3 else THRESHOLD_OTSU

    print(f"\n{'='*60}")
    print("LIVING CLOCK - BLACK & WHITE CONVERSION")
    print(f"{'='*60}\n")

    process_directory(input_dir, output_dir, '*_dither.png', method)
