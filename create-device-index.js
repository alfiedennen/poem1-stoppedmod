/**
 * Create device-time-index.json for Living Clock firmware
 * Groups images by time code for efficient device lookup
 */

const fs = require('fs');
const path = require('path');

const CROPPED_DIR = path.join(__dirname, '../croppedimages');
const OUTPUT_FILE = path.join(__dirname, 'device-time-index.json');
const BASE_URL = 'https://stoppedclocks.org/living-clock/images/';

// Get all threshold images
const files = fs.readdirSync(CROPPED_DIR)
    .filter(f => f.endsWith('_threshold.png'))
    .sort();

console.log(`Found ${files.length} threshold images`);

// Group by time code (HHMM)
const timeMap = new Map();

for (const file of files) {
    // Extract time from filename (first 4 chars)
    const timeCode = file.substring(0, 4);

    if (!timeMap.has(timeCode)) {
        timeMap.set(timeCode, []);
    }

    timeMap.get(timeCode).push(BASE_URL + file);
}

// Convert to sorted array
const times = Array.from(timeMap.entries())
    .map(([time, images]) => ({ time, images }))
    .sort((a, b) => a.time.localeCompare(b.time));

const output = {
    generated: new Date().toISOString(),
    imageType: 'threshold',
    totalImages: files.length,
    uniqueTimes: times.length,
    times
};

fs.writeFileSync(OUTPUT_FILE, JSON.stringify(output, null, 2));

console.log(`\nCreated: ${OUTPUT_FILE}`);
console.log(`  Total images: ${files.length}`);
console.log(`  Unique times: ${times.length}`);
console.log(`  Time range: ${times[0]?.time} - ${times[times.length-1]?.time}`);
