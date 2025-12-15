/**
 * Create combined device index with text zones for Living Clock firmware
 * Merges device-time-index and text-zones into a single efficient JSON
 */

const fs = require('fs');
const path = require('path');

const TEXT_ZONES_FILE = path.join(__dirname, 'text-zones.json');
const OUTPUT_FILE = path.join(__dirname, 'living-clock-index.json');
const BASE_URL = 'https://stoppedclocks.org/living-clock/images/';

// Load text zones
const textZones = JSON.parse(fs.readFileSync(TEXT_ZONES_FILE, 'utf8'));

// Build combined index
const times = new Map();

for (const [filename, data] of Object.entries(textZones.images)) {
    // Extract time code from filename (first 4 chars)
    const timeCode = filename.substring(0, 4);

    if (!times.has(timeCode)) {
        times.set(timeCode, []);
    }

    // Build compact entry
    const entry = {
        url: BASE_URL + filename,
        // Text zone (compact format)
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
    v: 2,  // Version
    generated: new Date().toISOString(),
    stats: {
        times: timesArray.length,
        images: totalImages,
        withZones: withZones
    },
    times: timesArray
};

fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output));

// Also create a pretty-printed version for debugging
fs.writeFileSync(
    path.join(__dirname, 'living-clock-index-debug.json'),
    JSON.stringify(output, null, 2)
);

console.log(`\nCreated: ${OUTPUT_FILE}`);
console.log(`  Unique times: ${timesArray.length}`);
console.log(`  Total images: ${totalImages}`);
console.log(`  With text zones: ${withZones}`);
console.log(`  File size: ${(fs.statSync(OUTPUT_FILE).size / 1024).toFixed(1)} KB`);
