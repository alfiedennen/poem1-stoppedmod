# Living Clock M5PaperS3 Experiment Log

**Goal**: Get images displaying on the M5PaperS3 e-paper device

**Device**: M5PaperS3 (ESP32-S3, 16MB Flash, 8MB PSRAM, 960x540 EPD)

---

## Experiment 1: Minimal M5Unified/M5GFX Test v1
**Date**: 2025-12-14
**Firmware**: `poem1/living-clock/firmware/`

### What We Tried
- Basic M5Unified initialization with `M5.begin()`
- WiFi connection
- `M5.Display.drawJpgUrl()` call

### platformio.ini
```ini
platform = espressif32
board = esp32-s3-devkitm-1
lib_deps = M5Unified@0.2.2, M5GFX@0.2.7
```

### Result: FAIL - Boot Loop
- Device stuck in continuous reset loop (`rst:0x3 RTC_SW_SYS_RST`)
- Never reached our code - crashed during M5.begin()
- Root cause: M5GFX auto-detection crashing when probing I2C

---

## Experiment 2: M5Unified with NVS Clear + Explicit Config v2
**Date**: 2025-12-14

### Changes from v1
1. Added `nvs_flash_init()` before anything
2. Clear M5GFX NVS namespace (removes cached board type)
3. Disabled all external display probing in config
4. Added 2-second delay for USB CDC stabilization
5. Set `cfg.output_power = false`

### Result: FAIL - Still boot looping

---

## Experiment 3: Bare-Bones ESP32-S3 (NO M5 Libraries) v3
**Date**: 2025-12-14

### Changes from v2
1. **Removed ALL M5 libraries** - no M5Unified, no M5GFX
2. Just Arduino framework with WiFi and Serial
3. Kept PSRAM override (`board_build.arduino.memory_type = qio_opi`)

### What We Tried
```cpp
#include <Arduino.h>
#include <WiFi.h>
// NO M5 INCLUDES AT ALL

void setup() {
    Serial.begin(115200);
    delay(3000);
    Serial.println("ESP32-S3 Bare-Bones Test");
    // Basic system info + WiFi connect
}
```

### Result: FAIL - Still boot looping!

**Critical Finding**: The boot loop is NOT caused by M5GFX. Even a bare Arduino sketch won't boot.

---

## Experiment 4: Remove PSRAM Override v4
**Date**: 2025-12-14

### Changes from v3
1. Removed `board_build.arduino.memory_type = qio_opi` from platformio.ini
2. Only keeping `board_build.flash_size = 16MB`

### platformio.ini
```ini
[env:m5papers3]
platform = espressif32
board = esp32-s3-devkitm-1
framework = arduino
board_build.flash_size = 16MB
board_build.partitions = default_16MB.csv
monitor_speed = 115200
upload_speed = 921600
build_flags =
    -DARDUINO_USB_CDC_ON_BOOT=1
    -DCORE_DEBUG_LEVEL=3
lib_deps =
```

### Result: FAIL - Still boot looping

**Conclusion**: The `esp32-s3-devkitm-1` board definition is fundamentally incompatible with M5PaperS3 hardware. The device needs a specific board configuration that matches its actual hardware (PSRAM type, flash mode, etc.).

---

## Experiment 5: Restore Original Firmware
**Date**: 2025-12-14

### What We Tried
Flashed the complete 16MB original firmware backup:
```bash
esptool --chip esp32s3 --port COM3 write_flash 0x0 poem1/firmware/poem1_original_backup.bin
```

### Result: SUCCESS!

**Serial Output**:
```
Welcome to Poem/1
Build ID: ba4eb39
screenId: 20E12990A994
Device API root: https://poem.town/api/v1/clock
```

### Key Findings
1. **Hardware is FINE** - not a hardware issue
2. **Full flash restore works** - need bootloader + partition table + app
3. **esp32-s3-devkitm-1 board is incompatible** - causes boot loop
4. **Need correct board definition** for M5PaperS3

### Next Steps
- Find M5Stack's official M5PaperS3 board definition
- Or extract board config from original firmware

---

## Experiment 6: M5Unified with HelloWorld Config v5-v8
**Date**: 2025-12-14

### What We Tried
1. v5: Exact HelloWorld platformio.ini with M5Unified
2. v6: Serial debug before/after M5.begin()
3. v7: Status printing in loop
4. v8: Force board type with `#define M5GFX_BOARD board_M5PaperS3`

### Results
- Device boots successfully (no more boot loop!)
- PSRAM detected: 8,386,279 bytes (~8MB)
- **Display: 0x0** - M5GFX auto-detection still failing

### Key Finding
GT911 touch controller is not responding, causing M5GFX to skip M5PaperS3 initialization.

---

## Experiment 7: Custom Panel_EPD Init (bypass GT911) v9
**Date**: 2025-12-14

### What We Tried
Custom LGFX class that directly creates Panel_EPD and Bus_EPD with M5PaperS3 pin configuration, bypassing GT911 touch controller detection.

### platformio.ini
```ini
platform = espressif32
board = esp32-s3-devkitm-1
framework = arduino
board_build.partitions = default_16MB.csv
board_upload.flash_size = 16MB
board_build.arduino.memory_type = qio_opi
build_flags =
    -DBOARD_HAS_PSRAM
    -DCONFIG_ESP32S3_SPIRAM_SUPPORT
    -DCONFIG_SPIRAM_MODE_OCT
    -DARDUINO_USB_CDC_ON_BOOT=1
    -DCORE_DEBUG_LEVEL=3
lib_deps =
    m5stack/M5GFX@^0.2.17
```

### Code Pattern
```cpp
#include <M5GFX.h>
#include <lgfx/v1/platforms/esp32/Bus_EPD.h>
#include <lgfx/v1/platforms/esp32/Panel_EPD.hpp>

class LGFX_M5PaperS3 : public lgfx::LGFX_Device {
    lgfx::Bus_EPD _bus_instance;
    lgfx::Panel_EPD _panel_instance;
public:
    LGFX_M5PaperS3() {
        // Configure Bus_EPD with M5PaperS3 pins
        // Configure Panel_EPD with 960x540, line_padding=8
        setPanel(&_panel_instance);
    }
};
```

### Result: SUCCESS!

**Serial Output**:
```
Display: 540x960
```

The display is now correctly initialized at 540x960 (portrait mode)!

### Bus Pin Configuration (from M5GFX.cpp)
- Data pins: 6, 14, 7, 12, 9, 11, 8, 10
- pin_pwr: GPIO_NUM_46
- pin_spv: GPIO_NUM_17
- pin_ckv: GPIO_NUM_18
- pin_sph: GPIO_NUM_13
- pin_oe: GPIO_NUM_45
- pin_le: GPIO_NUM_15
- pin_cl: GPIO_NUM_16

---

## Key Technical Findings

### GT911 Touch Controller Issue
- M5GFX auto-detection probes I2C for GT911 touch controller
- If GT911 doesn't respond, Panel_EPD and Bus_EPD are never created
- Results in 0x0 display resolution
- Original poem.town firmware works - so hardware is fine

### M5GFX NVS Cache
- M5GFX caches detected board type in NVS as "board:X"
- If cached as "board_unknown" (0), compile-time defines are ignored
- Must clear before M5.begin() to allow fresh detection

### Include Order Critical
- `HTTPClient.h` MUST be included BEFORE `M5GFX.h`/`M5Unified.h`
- Otherwise `drawJpgUrl()` method is not available

---

## Experiment 8: WiFi + HTTPS Image Loading v10
**Date**: 2025-12-14

### What We Tried
1. Added WiFi connection (SSID: "Artpublic24ghz")
2. Switched from HTTP to HTTPS with `WiFiClientSecure` + `setInsecure()` (skip cert verification)
3. Used PSRAM buffer approach: download entire JPEG to `ps_malloc()` buffer, then draw

### Issues Encountered
- HTTP `placehold.co` returned 301 redirect to HTTPS
- Direct stream drawing (`display.drawJpg(&client, len)`) failed
- Needed to download to buffer first, then use `display.drawJpg(buffer, len, x, y, w, h)`

### Working Code Pattern
```cpp
WiFiClientSecure client;
client.setInsecure();  // Skip SSL cert verification

HTTPClient http;
http.begin(client, "https://placehold.co/960x540.jpg");
http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);

int httpCode = http.GET();
if (httpCode == HTTP_CODE_OK) {
    int len = http.getSize();
    uint8_t* buffer = (uint8_t*)ps_malloc(len);
    WiFiClient* stream = http.getStreamPtr();
    stream->readBytes(buffer, len);

    display.fillScreen(TFT_WHITE);
    display.drawJpg(buffer, len, 0, 0, 960, 540);
    display.display();
    free(buffer);
}
```

### Result: SUCCESS!
```
Connected! IP: 192.168.0.141
Loading: https://placehold.co/960x540.jpg
HTTP response code: 200
Image size: 9276 bytes
Downloaded 9276 bytes to PSRAM
Image drawn successfully!
```

### Key Learnings
1. **PSRAM buffer required**: Stream-based drawJpg doesn't work reliably with HTTPS
2. **Use ps_malloc()**: PSRAM allocation for large image buffers (~8MB available)
3. **HTTPS mandatory**: Most image hosts redirect HTTP to HTTPS
4. **setInsecure()**: Skip SSL cert verification for embedded devices

---

## Experiment 9: Dithered Images with 2x Scaling v11
**Date**: 2025-12-14

### What We Tried
1. Switched to dithered PNG images from `living-clock/images/` folder on S3
2. Discovered source images are 510x300, not 960x540
3. Added 2x scale factor to `drawPng()` to fill the 960x540 display

### Working Code
```cpp
display.drawPng(buffer, len, 0, 0, 960, 540, 0, 0, 2.0, 2.0);  // 2x scale
```

### Result: SUCCESS - Full Screen Display!
```
Loading: https://stoppedclocks.org/living-clock/images/0105_local-shop-for-local-people_dither.png
HTTP response code: 200
Image size: 86300 bytes
Downloaded 86300 bytes to PSRAM
Image drawn successfully!
```

Image now fills the entire 960x540 e-paper display.

---

## Summary: Working Living Clock Image Display

### Final Working Configuration

**platformio.ini**:
- `platform = espressif32`
- `board = esp32-s3-devkitm-1`
- `board_build.arduino.memory_type = qio_opi`
- `lib_deps = m5stack/M5GFX@^0.2.17`
- Build flags: `-DBOARD_HAS_PSRAM -DCONFIG_ESP32S3_SPIRAM_SUPPORT -DCONFIG_SPIRAM_MODE_OCT`

**Code Requirements**:
1. Custom `LGFX_M5PaperS3` class to bypass GT911 auto-detection
2. `WiFiClientSecure` with `setInsecure()` for HTTPS
3. PSRAM buffer via `ps_malloc()` before `drawPng()`
4. 2x scale factor for 510x300 → 960x540 display

### Image Pipeline

```
S3 Bucket: stoppedclocks-website/living-clock/images/
    ↓
CloudFront: https://stoppedclocks.org/living-clock/images/
    ↓
Firmware: WiFiClientSecure → PSRAM buffer → drawPng(2x scale)
    ↓
Display: 960x540 e-paper at 4-bit grayscale
```

---

## Next Steps

1. **Add time-based image selection** - Build URL from current HH:MM
2. **Create time index** - List available images for each time slot
3. **Deep sleep integration** - Wake every minute to update display
4. **Handle 12-hour clock** - AM/PM interpretations like web version
5. **Error handling** - WiFi reconnection, fallback images
