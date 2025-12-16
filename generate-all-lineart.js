/**
 * Generate line art for ALL threshold images
 * Uses Nano Banana Pro (Gemini 3) for image-to-image transformation
 *
 * Usage: node generate-all-lineart.js [--resume] [--limit=N]
 */

const fs = require('fs');
const path = require('path');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
if (!GEMINI_API_KEY) {
    console.error('ERROR: Set GEMINI_API_KEY environment variable');
    process.exit(1);
}
const MODEL = 'nano-banana-pro-preview';

const croppedDir = path.join(__dirname, 'croppedimages');
const outputDir = path.join(__dirname, 'lineart');
const progressFile = path.join(__dirname, 'lineart-progress.json');

// Rate limiting
const DELAY_BETWEEN_REQUESTS = 1500; // 1.5 seconds

function extractTimeFromFilename(filename) {
    const match = filename.match(/^(\d{2})(\d{2})_/);
    if (match) {
        const hours = parseInt(match[1], 10);
        const minutes = parseInt(match[2], 10);
        return { hours, minutes, formatted: `${hours}:${minutes.toString().padStart(2, '0')}` };
    }
    return null;
}

function buildPrompt(time) {
    return `Convert this dithered black and white image into a clean line drawing.

Style requirements:
- Clean black lines on pure white background
- Remove all dithering/stippling texture
- Maximum white space - only draw the clock tower, remove all other buildings and background elements

CLOCK HANDS - CRITICAL:
This clock shows the time ${time.formatted} (${time.hours} hours, ${time.minutes} minutes).
- The HOUR hand should point to ${time.hours} on the clock face
- The MINUTE hand should point to ${time.minutes} (which is at the ${Math.round(time.minutes / 5) || 12} position)
- Draw both hands at these EXACT positions
- The hour hand is shorter and thicker, the minute hand is longer and thinner

This is documenting a real stopped clock - the time ${time.formatted} is historically significant and must be accurate.`;
}

function loadProgress() {
    if (fs.existsSync(progressFile)) {
        return JSON.parse(fs.readFileSync(progressFile, 'utf8'));
    }
    return { completed: [], failed: [] };
}

function saveProgress(progress) {
    fs.writeFileSync(progressFile, JSON.stringify(progress, null, 2));
}

async function transformImage(inputPath, outputPath, time) {
    const imageBuffer = fs.readFileSync(inputPath);
    const base64Image = imageBuffer.toString('base64');

    const prompt = buildPrompt(time);

    const requestBody = {
        contents: [{
            parts: [
                { inline_data: { mime_type: 'image/png', data: base64Image } },
                { text: prompt }
            ]
        }],
        generationConfig: {
            responseModalities: ['TEXT', 'IMAGE']
        }
    };

    const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${GEMINI_API_KEY}`;

    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(`API Error ${response.status}: ${data.error?.message || JSON.stringify(data)}`);
    }

    if (data.candidates && data.candidates[0]?.content?.parts) {
        for (const part of data.candidates[0].content.parts) {
            if (part.inlineData) {
                const imageData = Buffer.from(part.inlineData.data, 'base64');
                fs.writeFileSync(outputPath, imageData);
                return imageData.length;
            }
        }
    }

    throw new Error('No image in response');
}

async function main() {
    const args = process.argv.slice(2);
    const resume = args.includes('--resume');
    const limitArg = args.find(a => a.startsWith('--limit='));
    const limit = limitArg ? parseInt(limitArg.split('=')[1], 10) : Infinity;

    console.log('=== Nano Banana Pro Line Art Generator ===\n');

    // Create output directory
    if (!fs.existsSync(outputDir)) {
        fs.mkdirSync(outputDir, { recursive: true });
        console.log(`Created output directory: ${outputDir}`);
    }

    // Get all threshold images
    const allImages = fs.readdirSync(croppedDir)
        .filter(f => f.endsWith('_threshold.png'))
        .sort();

    console.log(`Found ${allImages.length} threshold images`);

    // Load progress if resuming
    let progress = resume ? loadProgress() : { completed: [], failed: [] };

    if (resume && progress.completed.length > 0) {
        console.log(`Resuming: ${progress.completed.length} already completed, ${progress.failed.length} failed`);
    }

    // Filter out already completed
    const toProcess = allImages.filter(img => !progress.completed.includes(img));
    const actualLimit = Math.min(toProcess.length, limit);

    console.log(`Processing ${actualLimit} images...\n`);

    let success = 0;
    let failed = 0;
    const startTime = Date.now();

    for (let i = 0; i < actualLimit; i++) {
        const inputFile = toProcess[i];
        const outputFile = inputFile.replace('_threshold.png', '_lineart.png');

        const inputPath = path.join(croppedDir, inputFile);
        const outputPath = path.join(outputDir, outputFile);

        const time = extractTimeFromFilename(inputFile);
        if (!time) {
            console.log(`[${i + 1}/${actualLimit}] ⚠️  Skipping ${inputFile} - couldn't extract time`);
            progress.failed.push(inputFile);
            saveProgress(progress);
            failed++;
            continue;
        }

        const overallProgress = progress.completed.length + i + 1;
        const totalImages = allImages.length;
        const pct = ((overallProgress / totalImages) * 100).toFixed(1);

        process.stdout.write(`[${overallProgress}/${totalImages}] (${pct}%) ${time.formatted} ${inputFile.substring(0, 40)}...`);

        try {
            const outputSize = await transformImage(inputPath, outputPath, time);
            console.log(` ✅ ${(outputSize / 1024).toFixed(0)}KB`);
            progress.completed.push(inputFile);
            success++;
        } catch (error) {
            console.log(` ❌ ${error.message}`);
            progress.failed.push(inputFile);
            failed++;
        }

        saveProgress(progress);

        // Rate limiting
        if (i < actualLimit - 1) {
            await new Promise(r => setTimeout(r, DELAY_BETWEEN_REQUESTS));
        }
    }

    const elapsed = ((Date.now() - startTime) / 1000 / 60).toFixed(1);

    console.log('\n=== Complete ===');
    console.log(`This run: ${success} success, ${failed} failed`);
    console.log(`Overall: ${progress.completed.length}/${allImages.length} completed`);
    console.log(`Time: ${elapsed} minutes`);
    console.log(`Output: ${outputDir}`);

    if (progress.failed.length > 0) {
        console.log(`\nFailed images (${progress.failed.length}):`);
        progress.failed.slice(0, 10).forEach(f => console.log(`  - ${f}`));
        if (progress.failed.length > 10) {
            console.log(`  ... and ${progress.failed.length - 10} more`);
        }
    }
}

main().catch(err => console.error('Fatal error:', err));
