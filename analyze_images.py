"""
Living Clock Image Analysis

Analyzes clock images to:
1. Calculate available white/light space
2. Identify potential text placement zones
3. Generate metadata for firmware text positioning
"""

import os
import json
from pathlib import Path
from PIL import Image
import numpy as np

# Thresholds for 4-bit grayscale (16 levels)
# Level 15 = white, Level 0 = black
WHITE_THRESHOLD = 200  # Pixels above this are "white" (levels 13-15)
LIGHT_THRESHOLD = 160  # Pixels above this are "light" (levels 10-15)
DARK_THRESHOLD = 80    # Pixels below this are "dark" (levels 0-5)

def analyze_image(image_path):
    """Analyze a single image for text placement potential."""
    img = Image.open(image_path).convert('L')  # Convert to grayscale
    pixels = np.array(img)

    width, height = img.size
    total_pixels = width * height

    # Overall statistics
    white_pixels = np.sum(pixels >= WHITE_THRESHOLD)
    light_pixels = np.sum(pixels >= LIGHT_THRESHOLD)
    dark_pixels = np.sum(pixels <= DARK_THRESHOLD)

    # Histogram buckets (simulating 4-bit / 16 levels)
    hist_16 = np.histogram(pixels, bins=16, range=(0, 256))[0]

    # Regional analysis - divide into grid
    grid_rows, grid_cols = 3, 4  # 12 regions
    region_height = height // grid_rows
    region_width = width // grid_cols

    regions = []
    for row in range(grid_rows):
        for col in range(grid_cols):
            y1, y2 = row * region_height, (row + 1) * region_height
            x1, x2 = col * region_width, (col + 1) * region_width
            region = pixels[y1:y2, x1:x2]

            region_white = np.sum(region >= WHITE_THRESHOLD) / region.size
            region_light = np.sum(region >= LIGHT_THRESHOLD) / region.size
            region_mean = np.mean(region)

            regions.append({
                'row': row,
                'col': col,
                'x': x1,
                'y': y1,
                'width': region_width,
                'height': region_height,
                'white_ratio': round(region_white, 3),
                'light_ratio': round(region_light, 3),
                'mean_brightness': round(region_mean, 1),
                'text_suitable': bool(region_light > 0.6)  # 60%+ light = good for text
            })

    # Find best text zone (contiguous light regions)
    best_zones = sorted(regions, key=lambda r: r['light_ratio'], reverse=True)

    # Top and bottom strips (common text placement)
    top_strip = pixels[:height//4, :]
    bottom_strip = pixels[3*height//4:, :]

    top_light_ratio = np.sum(top_strip >= LIGHT_THRESHOLD) / top_strip.size
    bottom_light_ratio = np.sum(bottom_strip >= LIGHT_THRESHOLD) / bottom_strip.size

    return {
        'filename': os.path.basename(image_path),
        'dimensions': {'width': width, 'height': height},
        'overall': {
            'white_ratio': round(white_pixels / total_pixels, 3),
            'light_ratio': round(light_pixels / total_pixels, 3),
            'dark_ratio': round(dark_pixels / total_pixels, 3),
            'mean_brightness': round(np.mean(pixels), 1),
            'std_brightness': round(np.std(pixels), 1),
        },
        'histogram_16': hist_16.tolist(),
        'strips': {
            'top_quarter_light': round(top_light_ratio, 3),
            'bottom_quarter_light': round(bottom_light_ratio, 3),
        },
        'regions': regions,
        'best_text_zones': [r for r in best_zones[:3] if r['light_ratio'] > 0.5],
        'recommendation': get_recommendation(light_pixels/total_pixels, top_light_ratio, bottom_light_ratio)
    }

def get_recommendation(overall_light, top_light, bottom_light):
    """Generate text placement recommendation."""
    if top_light > 0.7:
        return 'TOP'
    elif bottom_light > 0.7:
        return 'BOTTOM'
    elif overall_light > 0.5:
        return 'OVERLAY_WITH_BOX'
    else:
        return 'NEEDS_PROCESSING'

def analyze_directory(dir_path, pattern='*_dither.png'):
    """Analyze all matching images in a directory."""
    results = []
    dir_path = Path(dir_path)

    for img_path in sorted(dir_path.glob(pattern)):
        print(f"Analyzing: {img_path.name}")
        try:
            analysis = analyze_image(img_path)
            results.append(analysis)
        except Exception as e:
            print(f"  Error: {e}")

    return results

def summarize_results(results):
    """Generate summary statistics."""
    if not results:
        return {}

    light_ratios = [r['overall']['light_ratio'] for r in results]
    recommendations = {}
    for r in results:
        rec = r['recommendation']
        recommendations[rec] = recommendations.get(rec, 0) + 1

    return {
        'total_images': len(results),
        'avg_light_ratio': round(np.mean(light_ratios), 3),
        'min_light_ratio': round(min(light_ratios), 3),
        'max_light_ratio': round(max(light_ratios), 3),
        'recommendations': recommendations,
        'images_needing_processing': [r['filename'] for r in results if r['recommendation'] == 'NEEDS_PROCESSING']
    }

if __name__ == '__main__':
    import sys

    # Default to croppedimages directory
    img_dir = sys.argv[1] if len(sys.argv) > 1 else '../croppedimages'

    print(f"\n=== Living Clock Image Analysis ===\n")
    print(f"Directory: {img_dir}")
    print(f"Thresholds: WHITE>{WHITE_THRESHOLD}, LIGHT>{LIGHT_THRESHOLD}, DARK<{DARK_THRESHOLD}\n")

    # Analyze dithered images
    print("--- Analyzing Dithered Images ---")
    dithered = analyze_directory(img_dir, '*_dither.png')

    # Analyze non-dithered if they exist
    print("\n--- Analyzing Non-Dithered Images ---")
    non_dithered = analyze_directory(img_dir, '[0-9][0-9][0-9][0-9]_*.png')
    # Filter out dithered from non-dithered
    non_dithered = [r for r in non_dithered if '_dither' not in r['filename']]

    # Summary
    print("\n=== SUMMARY ===\n")

    if dithered:
        summary = summarize_results(dithered)
        print("Dithered Images:")
        print(f"  Total: {summary['total_images']}")
        print(f"  Avg light ratio: {summary['avg_light_ratio']}")
        print(f"  Range: {summary['min_light_ratio']} - {summary['max_light_ratio']}")
        print(f"  Recommendations: {summary['recommendations']}")
        if summary['images_needing_processing']:
            print(f"  Need processing: {len(summary['images_needing_processing'])} images")

    if non_dithered:
        summary = summarize_results(non_dithered)
        print("\nNon-Dithered Images:")
        print(f"  Total: {summary['total_images']}")
        print(f"  Avg light ratio: {summary['avg_light_ratio']}")

    # Save detailed results
    output = {
        'dithered': dithered,
        'non_dithered': non_dithered,
        'summary': {
            'dithered': summarize_results(dithered),
            'non_dithered': summarize_results(non_dithered)
        }
    }

    # Convert numpy types to native Python for JSON
    def convert_types(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, dict):
            return {k: convert_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_types(i) for i in obj]
        return obj

    output = convert_types(output)

    output_path = Path(img_dir) / 'image_analysis.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nDetailed results saved to: {output_path}")

    # Print images needing processing with their stats
    print("\n=== IMAGES NEEDING PROCESSING ===\n")
    needs_processing = [r for r in dithered if r['recommendation'] == 'NEEDS_PROCESSING']
    for img in sorted(needs_processing, key=lambda x: x['overall']['light_ratio'])[:20]:
        print(f"  {img['filename'][:50]:50} light={img['overall']['light_ratio']:.2f} mean={img['overall']['mean_brightness']:.0f}")
