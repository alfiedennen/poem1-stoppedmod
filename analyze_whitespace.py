"""
Living Clock Whitespace Analysis

Finds contiguous white regions suitable for text rendering.
Black pixels are treated as barriers that text cannot cross.

Algorithm:
1. Push light grays → white (expand available whitespace)
2. Identify black pixels as impassable barriers
3. Find largest contiguous white rectangles
4. Score regions by usable text area
"""

import os
import json
from pathlib import Path
from PIL import Image
import numpy as np
from scipy import ndimage

# Thresholds - STRICT settings for clean lineart images
# New lineart has crisp black lines on pure white - text must NOT intersect black pixels
PUSH_TO_WHITE_THRESHOLD = 250  # For lineart: only pure white (>=250) is safe
BLACK_BARRIER_THRESHOLD = 200  # For lineart: anything darker than 200 is a barrier
WHITE_VALUE = 255
MIN_TEXT_WIDTH = 100   # Minimum usable width for text (pixels)
MIN_TEXT_HEIGHT = 40   # Minimum usable height for text line
SAFETY_MARGIN_PX = 16  # Pixel margin around black lines (2 cells * 8px)


def find_largest_white_rectangle(binary_map):
    """
    Find the largest rectangle containing only white (1s) in a binary map.
    Uses the maximal rectangle in histogram algorithm.

    Returns: (x, y, width, height, area)
    """
    if binary_map.size == 0:
        return (0, 0, 0, 0, 0)

    rows, cols = binary_map.shape

    # Build height map (consecutive 1s above each cell)
    heights = np.zeros((rows, cols), dtype=int)
    for i in range(rows):
        for j in range(cols):
            if binary_map[i, j] == 1:
                heights[i, j] = heights[i-1, j] + 1 if i > 0 else 1
            else:
                heights[i, j] = 0

    max_area = 0
    best_rect = (0, 0, 0, 0, 0)

    # For each row, find largest rectangle in histogram
    for i in range(rows):
        rect = largest_rectangle_in_histogram(heights[i], i)
        if rect[4] > max_area:
            max_area = rect[4]
            best_rect = rect

    return best_rect


def largest_rectangle_in_histogram(heights, row_idx):
    """
    Find largest rectangle in histogram (standard algorithm).
    Returns: (x, y, width, height, area)
    """
    stack = []
    max_area = 0
    best_rect = (0, 0, 0, 0, 0)

    heights = list(heights) + [0]  # Append 0 to flush stack

    for i, h in enumerate(heights):
        start = i
        while stack and stack[-1][1] > h:
            idx, height = stack.pop()
            width = i - idx
            area = height * width
            if area > max_area:
                max_area = area
                # y is row_idx - height + 1 (top of rectangle)
                best_rect = (idx, row_idx - height + 1, width, height, area)
            start = idx
        stack.append((start, h))

    return best_rect


def find_top_n_rectangles(binary_map, n=5, min_width=MIN_TEXT_WIDTH, min_height=MIN_TEXT_HEIGHT):
    """
    Find the top N largest white rectangles.
    Uses iterative approach: find largest, mark as used, repeat.
    """
    rectangles = []
    work_map = binary_map.copy()

    for _ in range(n):
        rect = find_largest_white_rectangle(work_map)
        x, y, w, h, area = rect

        if w < min_width or h < min_height or area == 0:
            break

        rectangles.append({
            'x': int(x),
            'y': int(y),
            'width': int(w),
            'height': int(h),
            'area': int(area)
        })

        # Mark this rectangle as used (set to 0)
        work_map[y:y+h, x:x+w] = 0

    return rectangles


def analyze_image(image_path, push_threshold=PUSH_TO_WHITE_THRESHOLD,
                  barrier_threshold=BLACK_BARRIER_THRESHOLD):
    """
    Analyze a single image for text-suitable whitespace.

    For lineart images: finds zones that are completely white with NO black pixels.
    Uses safety margin to keep text away from line edges.
    """
    img = Image.open(image_path).convert('L')
    pixels = np.array(img)

    width, height = img.size

    # Step 1: For lineart, we don't "push" - we need strict white detection
    # Only pixels >= push_threshold are considered white
    pushed = pixels.copy()

    # Step 2: Create binary map (1 = white/safe, 0 = barrier/unsafe)
    # For lineart: ANY dark pixel is a barrier
    binary_map = np.zeros_like(pushed, dtype=np.uint8)
    binary_map[pixels >= push_threshold] = 1  # Pure white = safe
    binary_map[pixels <= barrier_threshold] = 0  # Any dark pixel = barrier

    # Step 2.5: Apply safety margin - dilate barriers to keep text away from edges
    if SAFETY_MARGIN_PX > 0:
        barrier_mask = (pixels <= barrier_threshold)
        # Dilate barrier mask
        struct_size = SAFETY_MARGIN_PX * 2 + 1
        struct = np.ones((struct_size, struct_size))
        expanded_barriers = ndimage.binary_dilation(barrier_mask, structure=struct)
        binary_map[expanded_barriers] = 0

    # Step 3: Find contiguous white regions
    labeled, num_features = ndimage.label(binary_map)

    # Get stats for each region
    regions = []
    for region_id in range(1, num_features + 1):
        region_mask = (labeled == region_id)
        region_size = np.sum(region_mask)

        # Get bounding box
        rows = np.any(region_mask, axis=1)
        cols = np.any(region_mask, axis=0)
        if not np.any(rows) or not np.any(cols):
            continue

        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]

        regions.append({
            'id': region_id,
            'pixel_count': int(region_size),
            'bbox': {
                'x': int(cmin),
                'y': int(rmin),
                'width': int(cmax - cmin + 1),
                'height': int(rmax - rmin + 1)
            },
            'fill_ratio': round(region_size / ((cmax - cmin + 1) * (rmax - rmin + 1)), 3)
        })

    # Sort by pixel count
    regions = sorted(regions, key=lambda r: r['pixel_count'], reverse=True)

    # Step 4: Find largest rectangles for text
    text_zones = find_top_n_rectangles(binary_map, n=5)

    # Step 5: Calculate overall stats
    total_white = np.sum(binary_map == 1)
    total_barrier = np.sum(pixels <= barrier_threshold)

    # Identify best text placement strategy
    if text_zones:
        best = text_zones[0]
        if best['y'] < height // 3:
            strategy = 'TOP'
        elif best['y'] > 2 * height // 3:
            strategy = 'BOTTOM'
        elif best['x'] < width // 3:
            strategy = 'LEFT'
        elif best['x'] > 2 * width // 3:
            strategy = 'RIGHT'
        else:
            strategy = 'CENTER'
    else:
        strategy = 'NO_SUITABLE_ZONE'

    return {
        'filename': os.path.basename(image_path),
        'dimensions': {'width': width, 'height': height},
        'stats': {
            'white_pixels': int(total_white),
            'white_ratio': round(total_white / (width * height), 3),
            'barrier_pixels': int(total_barrier),
            'barrier_ratio': round(total_barrier / (width * height), 3),
            'num_contiguous_regions': num_features,
        },
        'text_zones': text_zones,
        'best_strategy': strategy,
        'largest_regions': regions[:5] if regions else []
    }


def analyze_directory(dir_path, pattern='*_dither.png'):
    """Analyze all images in directory."""
    results = []
    dir_path = Path(dir_path)

    for img_path in sorted(dir_path.glob(pattern)):
        print(f"Analyzing: {img_path.name[:60]}")
        try:
            analysis = analyze_image(img_path)
            results.append(analysis)
        except Exception as e:
            print(f"  Error: {e}")

    return results


def print_summary(results):
    """Print summary of analysis."""
    if not results:
        print("No results to summarize")
        return

    strategies = {}
    zone_areas = []

    for r in results:
        s = r['best_strategy']
        strategies[s] = strategies.get(s, 0) + 1

        if r['text_zones']:
            zone_areas.append(r['text_zones'][0]['area'])

    print(f"\n{'='*60}")
    print("WHITESPACE ANALYSIS SUMMARY")
    print(f"{'='*60}")
    print(f"\nTotal images analyzed: {len(results)}")
    print(f"\nText placement strategies:")
    for strategy, count in sorted(strategies.items(), key=lambda x: -x[1]):
        print(f"  {strategy:20} {count:4} ({100*count/len(results):.1f}%)")

    if zone_areas:
        print(f"\nLargest text zone areas:")
        print(f"  Min:  {min(zone_areas):,} pixels")
        print(f"  Max:  {max(zone_areas):,} pixels")
        print(f"  Avg:  {int(np.mean(zone_areas)):,} pixels")
        print(f"  Med:  {int(np.median(zone_areas)):,} pixels")

    # Show images with smallest text zones
    print(f"\n{'='*60}")
    print("IMAGES WITH SMALLEST TEXT ZONES (may need processing)")
    print(f"{'='*60}\n")

    sorted_by_zone = sorted(results, key=lambda r: r['text_zones'][0]['area'] if r['text_zones'] else 0)
    for r in sorted_by_zone[:15]:
        zone_area = r['text_zones'][0]['area'] if r['text_zones'] else 0
        zone_dims = f"{r['text_zones'][0]['width']}x{r['text_zones'][0]['height']}" if r['text_zones'] else "N/A"
        print(f"  {r['filename'][:45]:45} zone={zone_area:6,}px ({zone_dims})")

    # Show images with largest text zones
    print(f"\n{'='*60}")
    print("IMAGES WITH LARGEST TEXT ZONES (good for text)")
    print(f"{'='*60}\n")

    for r in sorted_by_zone[-10:]:
        zone_area = r['text_zones'][0]['area'] if r['text_zones'] else 0
        zone = r['text_zones'][0] if r['text_zones'] else None
        if zone:
            print(f"  {r['filename'][:45]:45} zone={zone_area:6,}px @ ({zone['x']},{zone['y']}) {zone['width']}x{zone['height']}")


if __name__ == '__main__':
    import sys

    img_dir = sys.argv[1] if len(sys.argv) > 1 else '../croppedimages'

    print(f"\n{'='*60}")
    print("LIVING CLOCK WHITESPACE ANALYSIS")
    print(f"{'='*60}")
    print(f"\nDirectory: {img_dir}")
    print(f"Push to white threshold: >= {PUSH_TO_WHITE_THRESHOLD}")
    print(f"Barrier threshold: <= {BLACK_BARRIER_THRESHOLD}")
    print(f"Min text zone: {MIN_TEXT_WIDTH}x{MIN_TEXT_HEIGHT}\n")

    results = analyze_directory(img_dir, '*_dither.png')

    print_summary(results)

    # Save results
    output_path = Path(img_dir) / 'whitespace_analysis.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to: {output_path}")
