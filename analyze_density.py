"""
Living Clock Dither Density Analysis

For dithered images, analyzes local pixel density rather than contiguous whitespace.
A "white zone" in a dithered image is an area where the white:black ratio is high.

Algorithm:
1. Divide image into grid cells (e.g., 16x16 pixel blocks)
2. Calculate white pixel ratio per cell
3. Find regions where density exceeds threshold
4. Identify largest low-density (dark) regions as "barriers"
5. Output text zones as high-density areas avoiding barriers
"""

import os
import json
from pathlib import Path
from PIL import Image
import numpy as np

# Analysis parameters
CELL_SIZE = 8  # Analyze in 8x8 pixel blocks
WHITE_THRESHOLD = 200  # Individual pixel is "white"
BLACK_THRESHOLD = 60   # Individual pixel is "black"

# Zone classification
HIGH_DENSITY = 0.70   # 70%+ white pixels = good for text
MEDIUM_DENSITY = 0.50 # 50-70% white = marginal
LOW_DENSITY = 0.30    # <30% white = dark barrier

# Minimum zone dimensions (in cells)
MIN_ZONE_CELLS_W = 15  # 15 cells * 8px = 120px minimum width
MIN_ZONE_CELLS_H = 5   # 5 cells * 8px = 40px minimum height


def analyze_image(image_path):
    """Analyze dither density for text zone identification."""
    img = Image.open(image_path).convert('L')
    pixels = np.array(img)

    height, width = pixels.shape

    # Create density grid
    grid_h = height // CELL_SIZE
    grid_w = width // CELL_SIZE

    density_grid = np.zeros((grid_h, grid_w))
    barrier_grid = np.zeros((grid_h, grid_w), dtype=bool)

    for gy in range(grid_h):
        for gx in range(grid_w):
            y1, y2 = gy * CELL_SIZE, (gy + 1) * CELL_SIZE
            x1, x2 = gx * CELL_SIZE, (gx + 1) * CELL_SIZE
            cell = pixels[y1:y2, x1:x2]

            white_count = np.sum(cell >= WHITE_THRESHOLD)
            black_count = np.sum(cell <= BLACK_THRESHOLD)
            total = cell.size

            density_grid[gy, gx] = white_count / total

            # Mark as barrier if high black density (likely edge/border)
            barrier_grid[gy, gx] = (black_count / total) > 0.5

    # Find contiguous high-density zones
    high_density_mask = density_grid >= HIGH_DENSITY

    # Find largest rectangular high-density zone (avoiding barriers)
    usable_mask = high_density_mask & ~barrier_grid

    zones = find_density_zones(usable_mask, density_grid, barrier_grid)

    # Horizontal strip analysis (top, middle, bottom thirds)
    third_h = grid_h // 3
    strips = {
        'top': {
            'avg_density': float(np.mean(density_grid[:third_h, :])),
            'high_density_ratio': float(np.mean(high_density_mask[:third_h, :])),
            'barrier_ratio': float(np.mean(barrier_grid[:third_h, :]))
        },
        'middle': {
            'avg_density': float(np.mean(density_grid[third_h:2*third_h, :])),
            'high_density_ratio': float(np.mean(high_density_mask[third_h:2*third_h, :])),
            'barrier_ratio': float(np.mean(barrier_grid[third_h:2*third_h, :]))
        },
        'bottom': {
            'avg_density': float(np.mean(density_grid[2*third_h:, :])),
            'high_density_ratio': float(np.mean(high_density_mask[2*third_h:, :])),
            'barrier_ratio': float(np.mean(barrier_grid[2*third_h:, :]))
        }
    }

    # Find best strip for text
    best_strip = max(strips.items(),
                     key=lambda x: x[1]['high_density_ratio'] - x[1]['barrier_ratio'])

    # Overall stats
    overall_density = float(np.mean(density_grid))
    overall_barrier = float(np.mean(barrier_grid))

    return {
        'filename': os.path.basename(image_path),
        'dimensions': {'width': width, 'height': height},
        'grid': {'rows': grid_h, 'cols': grid_w, 'cell_size': CELL_SIZE},
        'overall': {
            'avg_density': round(overall_density, 3),
            'barrier_ratio': round(overall_barrier, 3),
            'high_density_cells': int(np.sum(high_density_mask)),
            'total_cells': grid_h * grid_w
        },
        'strips': strips,
        'best_strip': best_strip[0],
        'best_strip_score': round(best_strip[1]['high_density_ratio'] - best_strip[1]['barrier_ratio'], 3),
        'text_zones': zones,
        'recommendation': get_recommendation(strips, zones, overall_density)
    }


def find_density_zones(usable_mask, density_grid, barrier_grid):
    """Find rectangular zones suitable for text."""
    zones = []
    grid_h, grid_w = usable_mask.shape

    # Scan for largest rectangles using modified histogram method
    # First, find runs of usable cells in each row
    best_zones = []

    # Check horizontal strips at different y positions
    for start_y in range(grid_h - MIN_ZONE_CELLS_H + 1):
        for end_y in range(start_y + MIN_ZONE_CELLS_H, min(start_y + 20, grid_h + 1)):
            # Find longest continuous run in this horizontal band
            zone_height = end_y - start_y

            # For each column, check if ALL cells in this band are usable
            col_usable = np.all(usable_mask[start_y:end_y, :], axis=0)

            # Find runs of True values
            runs = find_runs(col_usable)

            for run_start, run_len in runs:
                if run_len >= MIN_ZONE_CELLS_W:
                    area = run_len * zone_height
                    avg_density = float(np.mean(density_grid[start_y:end_y, run_start:run_start+run_len]))

                    zones.append({
                        'x': run_start * CELL_SIZE,
                        'y': start_y * CELL_SIZE,
                        'width': run_len * CELL_SIZE,
                        'height': zone_height * CELL_SIZE,
                        'cells': run_len * zone_height,
                        'area_px': run_len * zone_height * CELL_SIZE * CELL_SIZE,
                        'avg_density': round(avg_density, 3)
                    })

    # Sort by area and return top 5
    zones.sort(key=lambda z: z['area_px'], reverse=True)
    return zones[:5]


def find_runs(bool_array):
    """Find runs of True values in a boolean array."""
    runs = []
    in_run = False
    run_start = 0

    for i, val in enumerate(bool_array):
        if val and not in_run:
            in_run = True
            run_start = i
        elif not val and in_run:
            in_run = False
            runs.append((run_start, i - run_start))

    if in_run:
        runs.append((run_start, len(bool_array) - run_start))

    return runs


def get_recommendation(strips, zones, overall_density):
    """Generate text placement recommendation."""
    # Find best strip
    best = max(strips.items(),
               key=lambda x: x[1]['high_density_ratio'] - x[1]['barrier_ratio'])

    strip_name, strip_data = best
    score = strip_data['high_density_ratio'] - strip_data['barrier_ratio']

    if zones and zones[0]['area_px'] > 10000:
        if zones[0]['y'] < 100:
            return 'ZONE_TOP'
        elif zones[0]['y'] > 200:
            return 'ZONE_BOTTOM'
        else:
            return 'ZONE_MIDDLE'
    elif score > 0.3:
        return f'STRIP_{strip_name.upper()}'
    elif overall_density > 0.5:
        return 'OVERLAY_WITH_BG'
    else:
        return 'DARK_IMAGE'


def analyze_directory(dir_path, pattern='*_dither.png'):
    """Analyze all images in directory."""
    results = []
    dir_path = Path(dir_path)

    for img_path in sorted(dir_path.glob(pattern)):
        print(f"Analyzing: {img_path.name[:55]}")
        try:
            analysis = analyze_image(img_path)
            results.append(analysis)
        except Exception as e:
            print(f"  Error: {e}")

    return results


def print_summary(results):
    """Print analysis summary."""
    if not results:
        return

    print(f"\n{'='*70}")
    print("DITHER DENSITY ANALYSIS SUMMARY")
    print(f"{'='*70}")
    print(f"\nTotal images: {len(results)}")

    # Recommendations breakdown
    recs = {}
    for r in results:
        rec = r['recommendation']
        recs[rec] = recs.get(rec, 0) + 1

    print("\nRecommendations:")
    for rec, count in sorted(recs.items(), key=lambda x: -x[1]):
        pct = 100 * count / len(results)
        print(f"  {rec:20} {count:4} ({pct:.1f}%)")

    # Strip analysis
    strip_winners = {'top': 0, 'middle': 0, 'bottom': 0}
    for r in results:
        strip_winners[r['best_strip']] += 1

    print("\nBest strip for text:")
    for strip, count in sorted(strip_winners.items(), key=lambda x: -x[1]):
        print(f"  {strip:10} {count:4} ({100*count/len(results):.1f}%)")

    # Density distribution
    densities = [r['overall']['avg_density'] for r in results]
    print(f"\nOverall density stats:")
    print(f"  Min: {min(densities):.2f}")
    print(f"  Max: {max(densities):.2f}")
    print(f"  Avg: {np.mean(densities):.2f}")

    # Show problematic images (low density, high barriers)
    print(f"\n{'='*70}")
    print("IMAGES WITH BEST TEXT ZONES")
    print(f"{'='*70}\n")

    sorted_by_zone = sorted(results,
                            key=lambda r: r['text_zones'][0]['area_px'] if r['text_zones'] else 0,
                            reverse=True)

    for r in sorted_by_zone[:15]:
        if r['text_zones']:
            z = r['text_zones'][0]
            print(f"  {r['filename'][:40]:40} {z['width']:3}x{z['height']:<3} @ ({z['x']:3},{z['y']:3}) density={z['avg_density']:.2f}")
        else:
            print(f"  {r['filename'][:40]:40} NO ZONE")

    print(f"\n{'='*70}")
    print("DARKEST IMAGES (may need special handling)")
    print(f"{'='*70}\n")

    sorted_by_density = sorted(results, key=lambda r: r['overall']['avg_density'])
    for r in sorted_by_density[:15]:
        print(f"  {r['filename'][:45]:45} density={r['overall']['avg_density']:.2f} barrier={r['overall']['barrier_ratio']:.2f}")


if __name__ == '__main__':
    import sys

    img_dir = sys.argv[1] if len(sys.argv) > 1 else '../croppedimages'

    print(f"\n{'='*70}")
    print("LIVING CLOCK DITHER DENSITY ANALYSIS")
    print(f"{'='*70}")
    print(f"\nDirectory: {img_dir}")
    print(f"Cell size: {CELL_SIZE}x{CELL_SIZE} pixels")
    print(f"High density threshold: {HIGH_DENSITY*100:.0f}%+ white pixels")
    print(f"Min zone size: {MIN_ZONE_CELLS_W*CELL_SIZE}x{MIN_ZONE_CELLS_H*CELL_SIZE} pixels\n")

    results = analyze_directory(img_dir, '*_dither.png')

    print_summary(results)

    # Save results
    output_path = Path(img_dir) / 'density_analysis.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to: {output_path}")
