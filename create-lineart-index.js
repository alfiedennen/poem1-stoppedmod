/**
 * Create device index for LINE ART images
 * Points to lineart folder instead of threshold images
 */

const fs = require('fs');
const path = require('path');

// Use device-resolution zones (510x300) for accurate text placement
const TEXT_ZONES_FILE = path.join(__dirname, 'text-zones-device.json');
const OUTPUT_FILE = path.join(__dirname, 'living-clock-index.json');
const DEBUG_FILE = path.join(__dirname, 'living-clock-index-debug.json');

// NEW: Point to lineart folder
const BASE_URL = 'https://stoppedclocks.org/living-clock/lineart/';

// Load text zones (still based on threshold analysis, zones should still be valid)
const textZones = JSON.parse(fs.readFileSync(TEXT_ZONES_FILE, 'utf8'));

// Build combined index
const times = new Map();

for (const [filename, data] of Object.entries(textZones.images)) {
    // Extract time code from filename (first 4 chars)
    const timeCode = filename.substring(0, 4);

    // Handle both lineart and threshold filenames
    let lineartFilename = filename;
    if (filename.includes('_threshold.png')) {
        lineartFilename = filename.replace('_threshold.png', '_lineart.png');
    }

    if (!times.has(timeCode)) {
        times.set(timeCode, []);
    }

    // Build compact entry
    const entry = {
        url: BASE_URL + lineartFilename,
        // Text zone (compact format) - still valid for lineart
        tz: data.zone ? {
            x: data.zone.x,
            y: data.zone.y,
            w: data.zone.width,
            h: data.zone.height
        } : null,
        // Fallback strip position
        strip: data.best_strip,
        // Recommendation
        rec: data.recommendation
    };

    times.get(timeCode).push(entry);
}

// Convert to sorted array
const timesArray = Array.from(times.entries())
    .map(([time, images]) => ({
        t: time,  // Compact key
        i: images // Compact key
    }))
    .sort((a, b) => a.t.localeCompare(b.t));

// Calculate stats
let totalImages = 0;
let withZones = 0;
for (const t of timesArray) {
    for (const img of t.i) {
        totalImages++;
        if (img.tz) withZones++;
    }
}

const output = {
    v: 3,  // Version 3 = lineart images
    type: 'lineart',
    generated: new Date().toISOString(),
    stats: {
        times: timesArray.length,
        images: totalImages,
        withZones: withZones
    },
    times: timesArray
};

fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output));
fs.writeFileSync(DEBUG_FILE, JSON.stringify(output, null, 2));

console.log(`\nCreated: ${OUTPUT_FILE}`);
console.log(`  Version: 3 (lineart)`);
console.log(`  Base URL: ${BASE_URL}`);
console.log(`  Unique times: ${timesArray.length}`);
console.log(`  Total images: ${totalImages}`);
console.log(`  With text zones: ${withZones}`);
console.log(`  File size: ${(fs.statSync(OUTPUT_FILE).size / 1024).toFixed(1)} KB`);
