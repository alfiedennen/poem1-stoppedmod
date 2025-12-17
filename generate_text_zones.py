"""
Generate Text Zone Metadata for Living Clock Images

Creates a JSON file mapping each image to its best text placement zone.
This metadata is used by the firmware to position text over clock images.

Output: text-zones.json
"""

import os
import json
from pathlib import Path
from PIL import Image
import numpy as np

# Analysis parameters - STRICT settings for clean lineart images
# New lineart has crisp black lines on pure white - text must NOT intersect black pixels
CELL_SIZE = 8
WHITE_THRESHOLD = 250       # For lineart: only pure white (>=250) is safe for text
BLACK_THRESHOLD = 200       # For lineart: anything darker than 200 is a line/barrier
HIGH_DENSITY = 0.98         # Require 98% white - almost pure white zones only
BLACK_TOLERANCE = 0.02      # Allow only 2% black in a cell - strict barrier detection
SAFETY_MARGIN = 2           # Extra cells of margin around black pixels
MIN_ZONE_WIDTH = 120
MIN_ZONE_HEIGHT = 40


def analyze_image_for_text_zone(image_path):
    """Analyze image and return best text zone.

    For lineart images: finds zones that are completely white with NO black pixels.
    Uses safety margin to keep text away from line edges.
    """
    img = Image.open(image_path).convert('L')
    pixels = np.array(img)
    height, width = pixels.shape

    grid_h = height // CELL_SIZE
    grid_w = width // CELL_SIZE

    # Build density grid - for lineart, we need STRICT white detection
    # A cell is only usable if it has essentially NO black pixels
    density_grid = np.zeros((grid_h, grid_w))
    barrier_grid = np.zeros((grid_h, grid_w), dtype=bool)  # Track cells with ANY black

    for gy in range(grid_h):
        for gx in range(grid_w):
            y1, y2 = gy * CELL_SIZE, (gy + 1) * CELL_SIZE
            x1, x2 = gx * CELL_SIZE, (gx + 1) * CELL_SIZE
            cell = pixels[y1:y2, x1:x2]
            white_count = np.sum(cell >= WHITE_THRESHOLD)
            black_count = np.sum(cell <= BLACK_THRESHOLD)
            total = cell.size

            # For lineart: ANY black pixel makes this cell a barrier
            black_ratio = black_count / total
            if black_ratio > BLACK_TOLERANCE:
                density_grid[gy, gx] = 0
                barrier_grid[gy, gx] = True
            else:
                density_grid[gy, gx] = white_count / total

    # Apply safety margin - expand barrier zones by SAFETY_MARGIN cells
    # This keeps text away from the edges of black lines
    from scipy import ndimage
    if SAFETY_MARGIN > 0:
        # Dilate barrier grid to create margin
        struct = np.ones((SAFETY_MARGIN * 2 + 1, SAFETY_MARGIN * 2 + 1))
        expanded_barriers = ndimage.binary_dilation(barrier_grid, structure=struct)
        # Zero out density where barriers expanded
        density_grid[expanded_barriers] = 0

    # Find usable zones - lower threshold to find more area
    high_density_mask = density_grid >= HIGH_DENSITY

    # Find largest rectangular zone
    best_zone = find_best_zone(high_density_mask, density_grid)

    # Calculate strip densities for fallback
    third_h = grid_h // 3
    strips = {
        'top': float(np.mean(density_grid[:third_h, :])),
        'middle': float(np.mean(density_grid[third_h:2*third_h, :])),
        'bottom': float(np.mean(density_grid[2*third_h:, :]))
    }

    best_strip = max(strips.items(), key=lambda x: x[1])

    return {
        'zone': best_zone,
        'strips': strips,
        'best_strip': best_strip[0],
        'overall_density': float(np.mean(density_grid))
    }


def find_best_zone(mask, density_grid):
    """Find best zone for text - maximize area for poem display."""
    grid_h, grid_w = mask.shape
    min_cells_w = MIN_ZONE_WIDTH // CELL_SIZE
    min_cells_h = MIN_ZONE_HEIGHT // CELL_SIZE

    best_zone = None
    best_score = 0

    for start_y in range(grid_h - min_cells_h + 1):
        for end_y in range(start_y + min_cells_h, grid_h + 1):
            zone_height = end_y - start_y
            col_usable = np.all(mask[start_y:end_y, :], axis=0)

            # Find runs of usable columns
            run_start = None
            for i in range(len(col_usable) + 1):
                if i < len(col_usable) and col_usable[i]:
                    if run_start is None:
                        run_start = i
                else:
                    if run_start is not None:
                        run_len = i - run_start
                        if run_len >= min_cells_w:
                            width_px = run_len * CELL_SIZE
                            height_px = zone_height * CELL_SIZE
                            area = width_px * height_px

                            # Score: use area (width * height) for balanced zones
                            # Poems need both width for text AND height for multiple lines
                            # Add small bonus for width to break ties
                            score = area + (width_px // 10)

                            # Only consider zones with reasonable minimum height (60px)
                            if height_px >= 60 and score > best_score:
                                best_score = score
                                avg_density = float(np.mean(
                                    density_grid[start_y:end_y, run_start:run_start+run_len]
                                ))
                                best_zone = {
                                    'x': run_start * CELL_SIZE,
                                    'y': start_y * CELL_SIZE,
                                    'width': width_px,
                                    'height': height_px,
                                    'area': area,
                                    'density': round(avg_density, 2)
                                }
                        run_start = None

    return best_zone


def generate_metadata(img_dir, output_path):
    """Generate metadata for all images."""
    img_dir = Path(img_dir)

    metadata = {
        'generated': None,
        'parameters': {
            'cell_size': CELL_SIZE,
            'white_threshold': WHITE_THRESHOLD,
            'black_threshold': BLACK_THRESHOLD,
            'high_density': HIGH_DENSITY,
            'min_zone_size': f'{MIN_ZONE_WIDTH}x{MIN_ZONE_HEIGHT}'
        },
        'images': {}
    }

    # Process lineart images first, then threshold, then dithered as fallback
    images = sorted(img_dir.glob('*_lineart.png'))
    if not images:
        images = sorted(img_dir.glob('*_threshold.png'))
    if not images:
        images = sorted(img_dir.glob('*_dither.png'))
    print(f"Processing {len(images)} images...")

    for i, img_path in enumerate(images):
        if i % 20 == 0:
            print(f"  {i}/{len(images)}...")

        try:
            analysis = analyze_image_for_text_zone(img_path)

            # Extract time from filename (first 4 chars)
            filename = img_path.name
            time_code = filename[:4]

            metadata['images'][filename] = {
                'time': f'{time_code[:2]}:{time_code[2:]}',
                'zone': analysis['zone'],
                'best_strip': analysis['best_strip'],
                'overall_density': round(analysis['overall_density'], 2),
                'recommendation': get_recommendation(analysis)
            }
        except Exception as e:
            print(f"  Error processing {img_path.name}: {e}")

    # Add generation timestamp
    from datetime import datetime
    metadata['generated'] = datetime.utcnow().isoformat() + 'Z'

    # Summary stats
    with_zones = sum(1 for img in metadata['images'].values() if img['zone'])
    metadata['summary'] = {
        'total_images': len(metadata['images']),
        'images_with_zones': with_zones,
        'images_without_zones': len(metadata['images']) - with_zones,
        'zone_coverage': f"{100*with_zones/len(metadata['images']):.1f}%"
    }

    # Write output
    with open(output_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\nGenerated: {output_path}")
    print(f"  Total images: {metadata['summary']['total_images']}")
    print(f"  With text zones: {metadata['summary']['images_with_zones']}")
    print(f"  Without zones: {metadata['summary']['images_without_zones']}")

    return metadata


def get_recommendation(analysis):
    """Get text placement recommendation."""
    if analysis['zone'] and analysis['zone']['area'] > 15000:
        if analysis['zone']['y'] < 80:
            return 'ZONE_TOP'
        elif analysis['zone']['y'] > 160:
            return 'ZONE_BOTTOM'
        else:
            return 'ZONE_CENTER'
    elif analysis['overall_density'] > 0.5:
        return f"STRIP_{analysis['best_strip'].upper()}"
    else:
        return 'DARK_OVERLAY'


if __name__ == '__main__':
    import sys

    img_dir = sys.argv[1] if len(sys.argv) > 1 else '../croppedimages'
    output = sys.argv[2] if len(sys.argv) > 2 else 'text-zones.json'

    print(f"\n=== Living Clock Text Zone Generator ===\n")
    print(f"Input: {img_dir}")
    print(f"Output: {output}\n")

    generate_metadata(img_dir, output)
