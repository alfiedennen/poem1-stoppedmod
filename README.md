# Poem/1: Stopped Clocks Mod

A mod for the [Poem/1](https://poem.town) e-paper device that displays AI-generated poems overlaid on photographs of stopped public clocks from [stoppedclocks.org](https://stoppedclocks.org).

![Living Clock Display](https://stoppedclocks.org/living-clock/images/preview.png)

## What This Is

The Poem/1 is an e-paper device by Acts Not Facts that displays time-specific AI-generated poetry. This mod replaces the standard display with photographs of stopped clocks showing the current time, with the poem overlaid in detected whitespace zones.

At 10:15, the device shows a photograph of a clock stopped at 10:15, with a poem about 10:15 rendered on the image.

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Poem/1 Device                                │
│                    (M5PaperS3 / ESP32-S3)                           │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                │ Every minute:
                                │
        ┌───────────────────────┴───────────────────────┐
        │                                               │
        ▼                                               ▼
┌───────────────────┐                      ┌───────────────────────┐
│   poem.town API   │                      │  stoppedclocks.org    │
│                   │                      │                       │
│ POST /api/v1/     │                      │ GET /living-clock/    │
│   clock/compose   │                      │  living-clock-index.  │
│                   │                      │       json            │
│ Returns:          │                      │                       │
│ - poem text       │                      │ Returns:              │
│ - font preference │                      │ - image URLs          │
└───────────────────┘                      │ - text zone coords    │
                                           └───────────────────────┘
```

## Hardware

**Target Device**: Poem/1 by Acts Not Facts (M5PaperS3 variant)

| Specification | Value |
|--------------|-------|
| MCU | ESP32-S3 with PSRAM |
| Display | ED047TC2 4.7" e-paper (960x540) |
| Color depth | 4-bit grayscale |
| Interface | 8-bit parallel EPD bus |
| Memory | 16MB flash, 8MB PSRAM |

## Key Technical Details

### Custom Display Driver

The M5PaperS3's GT911 touch controller doesn't respond on some units, which breaks M5GFX auto-detection. This firmware uses a custom `LGFX_M5PaperS3` class that directly initializes the display hardware:

```cpp
class LGFX_M5PaperS3 : public lgfx::LGFX_Device {
    // Explicit Bus_EPD and Panel_EPD configuration
    // Bypasses GT911 detection failure
};
```

### Image Loading

- Images served via CloudFront CDN
- Downloaded to PSRAM buffer before rendering (stream-based loading unreliable)
- Source images: 480x270 PNG, displayed at 2x scale (960x540)

### Text Zone Detection

Each clock image has pre-analyzed whitespace zones for poem placement:

```json
{
  "t": "0930",
  "i": [{
    "url": "https://stoppedclocks.org/living-clock/images/0930_clock-name.png",
    "tz": { "x": 0, "y": 0, "w": 256, "h": 296 },
    "strip": "top",
    "rec": "ZONE_TOP"
  }]
}
```

Zone analysis uses dither density detection (8x8 cell blocks) to find areas suitable for text overlay.

### Custom Font Rendering

The firmware supports custom TrueType fonts via OpenFontRender:

- **Inter** - Clean sans-serif for modern poems
- **Playfair Display** - Elegant serif for classic poems
- Fonts downloaded from CDN at boot (~500KB total)
- poem.town API returns `font` field ("INTER" or "PLAYFAIR")
- Font preference controlled via poem.town dashboard
- Dynamic font sizing: tries sizes 72→24px, picks largest that fits

### Text Rendering

The firmware automatically:
- Downloads and caches TTF fonts to PSRAM
- Re-wraps poem text using actual font metrics
- Tries font sizes 72→24px, picks largest that fits within 75% of zone
- Centers text in the detected whitespace zone
- Falls back to strip positioning if no zone detected
- Only reloads fonts when preference changes (prevents memory leaks)

### 12-Hour Time Matching

Clock faces show 12-hour format without AM/PM. The matching algorithm:
- Converts 24-hour current time to 12-hour
- Finds closest clock image (handles wraparound)
- Treats 10:15 clock as valid for both 10:15 AM and 10:15 PM

## File Structure

```
living-clock/
├── firmware/
│   ├── src/main.cpp        # Main firmware (~1000 lines)
│   └── platformio.ini      # Build configuration
├── generate_text_zones.py  # Whitespace analysis tool
├── create-combined-index.js # Index builder
├── text-zones.json         # Per-image zone data
├── living-clock-index.json # Combined time→image→zone index
├── LICENSE                 # MIT License
└── README.md               # This file
```

## Building

### Prerequisites

- [PlatformIO](https://platformio.org/) CLI or VSCode extension
- USB-C cable for flashing

### Configure WiFi

Edit `firmware/src/main.cpp`:

```cpp
const char* WIFI_SSID = "your-wifi-ssid";
const char* WIFI_PASS = "your-wifi-password";
```

### Build and Flash

```bash
cd firmware
pio run -t upload
```

### Monitor Serial Output

```bash
pio device monitor --baud 115200
```

## API Endpoints

### poem.town Compose API

```
POST https://poem.town/api/v1/clock/compose
Authorization: Bearer <token>
Content-Type: application/json

{ "screenId": "...", "time24": "09:30" }
```

Returns time-specific rhyming poem with font preference ("INTER" or "PLAYFAIR").

**Note**: The `screenId` must be the device MAC address in reverse byte order to match the poem.town dashboard format.

### Stopped Clocks Index

```
GET https://stoppedclocks.org/living-clock/living-clock-index.json
```

Returns compact time→image→zone mapping for firmware consumption.

## Data Sources

### Clock Images

- **Source**: [stoppedclocks.org](https://stoppedclocks.org) collection (200+ UK public clocks)
- **Processing**: Cropped to 480x270, converted to grayscale PNG
- **CDN**: CloudFront at `https://stoppedclocks.org/living-clock/images/`

### Fonts

- **Inter**: Downloaded from CDN (~412KB TTF)
- **Playfair Display**: Downloaded from CDN (~96KB TTF)
- **CDN**: `https://stoppedclocks.org/living-clock/fonts/`

### Text Zones

- **Generation**: `generate_text_zones.py` analyzes each image
- **Method**: Dither density analysis with 8x8 cell blocks
- **Coverage**: 99.6% of images have detected whitespace zones

## Dependencies

```ini
lib_deps =
    m5stack/M5GFX@^0.2.17
    bblanchon/ArduinoJson@^7.0.0
    https://github.com/takkaO/OpenFontRender.git
```

## Credits

- **poem.town** - AI poetry generation by [Acts Not Facts](https://www.actsnotfacts.com/)
- **Stopped Clocks** - Clock photography collection by [Alfie Dennen](https://stoppedclocks.org)
- **M5Stack** - M5PaperS3 hardware and M5GFX library
- **OpenFontRender** - TrueType font rendering by [takkaO](https://github.com/takkaO/OpenFontRender)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Related Projects

- [poem.town](https://poem.town) - The original Poem/1 service
- [stoppedclocks.org](https://stoppedclocks.org) - The Stopped Clocks archive
- [OpenFontRender](https://github.com/takkaO/OpenFontRender) - TrueType font rendering for Arduino

---

**Last Updated**: 2025-12-15
