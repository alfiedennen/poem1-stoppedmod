/**
 * M5PaperS3 Living Clock - Poems on Stopped Clock Images
 *
 * A "living clock" that displays poem.town poems overlaid on
 * photographs of stopped clocks showing the current time.
 *
 * Flow:
 * 1. Fetch poem from poem.town API
 * 2. Find clock image matching current time
 * 3. Render poem text in the image's whitespace zone
 * 4. Display on e-paper
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <M5GFX.h>
#include <lgfx/v1/platforms/esp32/Bus_EPD.h>
#include <lgfx/v1/platforms/esp32/Panel_EPD.hpp>
#include <ArduinoJson.h>
#include <time.h>
#include <OpenFontRender.h>

// Font rendering with OpenFontRender
// Inter = sans-serif (default), Playfair = serif
OpenFontRender fontRender;
bool fontsLoaded = false;
uint8_t* interFontData = nullptr;
uint8_t* playfairFontData = nullptr;
size_t interFontSize = 0;
size_t playfairFontSize = 0;

// Font URLs (hosted on stoppedclocks.org CDN)
// These are Inter Regular and Playfair Display Regular TTF files
const char* INTER_FONT_URL = "https://stoppedclocks.org/living-clock/fonts/Inter-Regular.ttf";
const char* PLAYFAIR_FONT_URL = "https://stoppedclocks.org/living-clock/fonts/PlayfairDisplay-Regular.ttf";

// WiFi credentials
const char* WIFI_SSID = "Artpublic24ghz";
const char* WIFI_PASS = "t33nwolf";

// NTP configuration (UK timezone)
const char* NTP_SERVER = "pool.ntp.org";
const long GMT_OFFSET_SEC = 0;
const int DAYLIGHT_OFFSET_SEC = 0;

// API URLs
const char* POEM_API_URL = "https://poem.town/api/v1/clock/compose";
const char* POEM_STATUS_URL = "https://poem.town/api/v1/clock/status";
const char* CLOCK_INDEX_URL = "https://stoppedclocks.org/living-clock/living-clock-index.json";

// Device ID (MAC-based)
String screenId;

// Clock image index storage
struct ClockImage {
    String url;
    int16_t zoneX, zoneY, zoneW, zoneH;  // Text zone coordinates
    String strip;  // Fallback: "top", "middle", "bottom"
};

struct TimeEntry {
    int timeCode;      // HHMM as integer
    ClockImage images[5];
    int imageCount;
};

TimeEntry clockIndex[200];
int clockIndexCount = 0;

// Current poem data
String currentPoem;
String currentFont;  // "INTER" or "PLAYFAIR"

// Custom LGFX class for M5PaperS3
class LGFX_M5PaperS3 : public lgfx::LGFX_Device
{
    lgfx::Bus_EPD _bus_instance;
    lgfx::Panel_EPD _panel_instance;

public:
    LGFX_M5PaperS3(void)
    {
        {
            auto cfg = _bus_instance.config();
            cfg.bus_speed = 16000000;
            cfg.pin_data[0] = GPIO_NUM_6;
            cfg.pin_data[1] = GPIO_NUM_14;
            cfg.pin_data[2] = GPIO_NUM_7;
            cfg.pin_data[3] = GPIO_NUM_12;
            cfg.pin_data[4] = GPIO_NUM_9;
            cfg.pin_data[5] = GPIO_NUM_11;
            cfg.pin_data[6] = GPIO_NUM_8;
            cfg.pin_data[7] = GPIO_NUM_10;
            cfg.pin_pwr = GPIO_NUM_46;
            cfg.pin_spv = GPIO_NUM_17;
            cfg.pin_ckv = GPIO_NUM_18;
            cfg.pin_sph = GPIO_NUM_13;
            cfg.pin_oe = GPIO_NUM_45;
            cfg.pin_le = GPIO_NUM_15;
            cfg.pin_cl = GPIO_NUM_16;
            cfg.bus_width = 8;
            _bus_instance.config(cfg);
            _panel_instance.setBus(&_bus_instance);
        }
        {
            auto cfg = _panel_instance.config_detail();
            cfg.line_padding = 8;
            _panel_instance.config_detail(cfg);
        }
        {
            auto cfg = _panel_instance.config();
            cfg.memory_width = 960;
            cfg.panel_width = 960;
            cfg.memory_height = 540;
            cfg.panel_height = 540;
            cfg.offset_rotation = 0;
            cfg.offset_x = 0;
            cfg.offset_y = 0;
            cfg.bus_shared = false;
            _panel_instance.config(cfg);
        }
        setPanel(&_panel_instance);
    }
};

LGFX_M5PaperS3 display;

// Track state
int lastDisplayedTime = -1;

/**
 * Get device screen ID from MAC address
 */
String getScreenId() {
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char macStr[13];
    snprintf(macStr, sizeof(macStr), "%02X%02X%02X%02X%02X%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    return String(macStr);
}

/**
 * Convert 24-hour time to 12-hour format
 */
int to12HourFormat(int hour24, int minute) {
    int hour12 = hour24 % 12;
    if (hour12 == 0) hour12 = 12;
    return hour12 * 100 + minute;
}

/**
 * Connect to WiFi
 */
bool connectWiFi() {
    Serial.print("Connecting to WiFi");
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("Connected! IP: %s\n", WiFi.localIP().toString().c_str());
        screenId = getScreenId();
        Serial.printf("Screen ID: %s\n", screenId.c_str());
        return true;
    }

    Serial.println("WiFi connection failed!");
    return false;
}

/**
 * Sync time with NTP
 */
bool syncTime() {
    Serial.println("Syncing time with NTP...");
    configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);

    struct tm timeinfo;
    int attempts = 0;
    while (!getLocalTime(&timeinfo) && attempts < 10) {
        delay(500);
        attempts++;
    }

    if (attempts >= 10) {
        Serial.println("NTP sync failed!");
        return false;
    }

    Serial.printf("Time synced: %02d:%02d:%02d\n",
                  timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
    return true;
}

/**
 * Get current time as HHMM integer (12-hour format)
 */
int getCurrentTimeCode() {
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) {
        return -1;
    }
    return to12HourFormat(timeinfo.tm_hour, timeinfo.tm_min);
}

/**
 * Get current time as HH:MM string (24-hour format for poem.town)
 */
String getCurrentTime24() {
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) {
        return "12:00";
    }
    char buf[6];
    snprintf(buf, sizeof(buf), "%02d:%02d", timeinfo.tm_hour, timeinfo.tm_min);
    return String(buf);
}

/**
 * Register device with poem.town
 * This must be called before fetching poems so the screenId is recognized
 */
bool registerWithPoemTown() {
    Serial.println("Registering with poem.town...");
    Serial.printf("Screen ID: %s\n", screenId.c_str());

    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    http.begin(client, POEM_STATUS_URL);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(15000);

    // Build JSON payload - note: status endpoint doesn't require auth
    JsonDocument doc;
    doc["screenId"] = screenId;
    doc["buildId"] = "living-clock-v1";

    String payload;
    serializeJson(doc, payload);
    Serial.printf("Status request: %s\n", payload.c_str());

    int httpCode = http.POST(payload);
    Serial.printf("poem.town /status response: %d\n", httpCode);

    if (httpCode == HTTP_CODE_OK) {
        String response = http.getString();
        Serial.printf("Status response: %s\n", response.c_str());

        // Parse to check if device is recognized
        JsonDocument resDoc;
        if (!deserializeJson(resDoc, response)) {
            bool success = resDoc["success"] | false;
            Serial.printf("Registration success: %s\n", success ? "yes" : "no");
        }
    } else if (httpCode < 0) {
        Serial.printf("HTTP error: %s\n", http.errorToString(httpCode).c_str());
    }

    http.end();
    return httpCode == HTTP_CODE_OK;
}

/**
 * Fetch poem from poem.town for current time
 */
bool fetchPoem(const String& time24) {
    Serial.printf("Fetching poem for %s from poem.town...\n", time24.c_str());

    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    http.begin(client, POEM_API_URL);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", "Bearer poem_HCWkTznfHFBN6H9KtQLCF9T");
    http.setTimeout(20000);

    // Build request - can use either screenId + time24, or just time24
    JsonDocument reqDoc;
    reqDoc["screenId"] = screenId;
    reqDoc["time24"] = time24;

    String payload;
    serializeJson(reqDoc, payload);
    Serial.printf("Compose request: %s\n", payload.c_str());

    int httpCode = http.POST(payload);
    Serial.printf("poem.town /compose response: %d\n", httpCode);

    if (httpCode != HTTP_CODE_OK) {
        if (httpCode < 0) {
            Serial.printf("HTTP error: %s\n", http.errorToString(httpCode).c_str());
        } else {
            String errorBody = http.getString();
            Serial.printf("Error body: %s\n", errorBody.c_str());
        }
        http.end();
        return false;
    }

    String response = http.getString();
    http.end();

    Serial.printf("Compose response: %s\n", response.substring(0, 200).c_str());

    // Parse response
    JsonDocument resDoc;
    DeserializationError error = deserializeJson(resDoc, response);
    if (error) {
        Serial.printf("JSON parse error: %s\n", error.c_str());
        return false;
    }

    // Extract poem - handle both string and potential null
    if (resDoc["poem"].is<const char*>()) {
        currentPoem = resDoc["poem"].as<String>();
    } else {
        Serial.println("No poem in response!");
        return false;
    }

    currentFont = resDoc["preferredFont"] | "INTER";

    Serial.printf("Poem received: \"%s\"\n", currentPoem.c_str());
    Serial.printf("Font: %s\n", currentFont.c_str());

    return currentPoem.length() > 0;
}

/**
 * Fetch clock image index from stoppedclocks.org
 */
bool fetchClockIndex() {
    Serial.println("Fetching clock index...");

    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    http.begin(client, CLOCK_INDEX_URL);
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
    http.setTimeout(20000);

    int httpCode = http.GET();
    Serial.printf("Clock index HTTP: %d\n", httpCode);

    if (httpCode != HTTP_CODE_OK) {
        http.end();
        return false;
    }

    String payload = http.getString();
    http.end();

    Serial.printf("Received %d bytes\n", payload.length());

    // Parse JSON
    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, payload);
    if (error) {
        Serial.printf("JSON error: %s\n", error.c_str());
        return false;
    }

    // Extract time entries
    JsonArray times = doc["times"];
    clockIndexCount = 0;

    for (JsonObject entry : times) {
        if (clockIndexCount >= 200) break;

        const char* timeStr = entry["t"];
        clockIndex[clockIndexCount].timeCode = atoi(timeStr);
        clockIndex[clockIndexCount].imageCount = 0;

        JsonArray images = entry["i"];
        for (JsonObject img : images) {
            int idx = clockIndex[clockIndexCount].imageCount;
            if (idx >= 5) break;

            clockIndex[clockIndexCount].images[idx].url = img["url"].as<String>();

            // Text zone
            if (img["tz"].is<JsonObject>()) {
                JsonObject tz = img["tz"];
                clockIndex[clockIndexCount].images[idx].zoneX = tz["x"];
                clockIndex[clockIndexCount].images[idx].zoneY = tz["y"];
                clockIndex[clockIndexCount].images[idx].zoneW = tz["w"];
                clockIndex[clockIndexCount].images[idx].zoneH = tz["h"];
            } else {
                clockIndex[clockIndexCount].images[idx].zoneX = -1;
            }

            clockIndex[clockIndexCount].images[idx].strip = img["strip"].as<String>();
            clockIndex[clockIndexCount].imageCount++;
        }
        clockIndexCount++;
    }

    Serial.printf("Loaded %d time entries\n", clockIndexCount);
    return clockIndexCount > 0;
}

/**
 * Find best matching clock image for a time
 */
ClockImage* findClockImage(int targetTime) {
    int bestIndex = -1;
    int bestDiff = 9999;

    for (int i = 0; i < clockIndexCount; i++) {
        int diff = abs(clockIndex[i].timeCode - targetTime);

        // Check wraparound
        int wrapDiff = 1200 - diff;
        if (wrapDiff > 0 && wrapDiff < diff) {
            diff = wrapDiff;
        }

        if (diff < bestDiff) {
            bestDiff = diff;
            bestIndex = i;
        }

        if (diff == 0) break;
    }

    if (bestIndex < 0) {
        return nullptr;
    }

    Serial.printf("Target: %04d, Found: %04d (diff: %d)\n",
                  targetTime, clockIndex[bestIndex].timeCode, bestDiff);

    // Random selection if multiple images
    int imageIdx = 0;
    if (clockIndex[bestIndex].imageCount > 1) {
        imageIdx = random(clockIndex[bestIndex].imageCount);
    }

    return &clockIndex[bestIndex].images[imageIdx];
}

/**
 * Download data to PSRAM buffer (for images or fonts)
 */
uint8_t* downloadToBuffer(const String& url, size_t& outLen, size_t maxSize = 500000) {
    Serial.printf("Downloading: %s\n", url.c_str());

    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    http.begin(client, url);
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
    http.setTimeout(30000);

    int httpCode = http.GET();
    if (httpCode != HTTP_CODE_OK) {
        Serial.printf("Download failed: %d\n", httpCode);
        http.end();
        return nullptr;
    }

    int len = http.getSize();
    if (len <= 0 || len > (int)maxSize) {
        Serial.printf("Invalid size: %d (max: %d)\n", len, maxSize);
        http.end();
        return nullptr;
    }

    uint8_t* buffer = (uint8_t*)ps_malloc(len);
    if (!buffer) {
        Serial.println("PSRAM alloc failed!");
        http.end();
        return nullptr;
    }

    WiFiClient* stream = http.getStreamPtr();
    size_t bytesRead = stream->readBytes(buffer, len);
    http.end();

    if (bytesRead != len) {
        Serial.printf("Read mismatch: %d vs %d\n", bytesRead, len);
        free(buffer);
        return nullptr;
    }

    outLen = len;
    Serial.printf("Downloaded %d bytes\n", len);
    return buffer;
}

/**
 * Download and load fonts from Google Fonts
 */
bool loadFonts() {
    Serial.println("Loading fonts from Google Fonts...");

    // Download Inter (sans-serif) - ~412KB
    Serial.println("Downloading Inter font...");
    interFontData = downloadToBuffer(INTER_FONT_URL, interFontSize, 600000);
    if (!interFontData) {
        Serial.println("Failed to download Inter font");
        return false;
    }

    // Download Playfair Display (serif) - ~96KB
    Serial.println("Downloading Playfair font...");
    playfairFontData = downloadToBuffer(PLAYFAIR_FONT_URL, playfairFontSize, 200000);
    if (!playfairFontData) {
        Serial.println("Failed to download Playfair font");
        // Continue with just Inter
    }

    // Set up OpenFontRender with display
    fontRender.setDrawer(display);

    // Load Inter as default font
    if (fontRender.loadFont(interFontData, interFontSize)) {
        Serial.println("ERROR: Failed to load Inter font into renderer");
        return false;
    }

    fontsLoaded = true;
    Serial.println("Fonts loaded successfully!");
    return true;
}

/**
 * Switch active font based on preference
 */
void setActiveFont(const String& fontName) {
    if (!fontsLoaded) return;

    if (fontName == "PLAYFAIR" && playfairFontData) {
        fontRender.loadFont(playfairFontData, playfairFontSize);
        Serial.println("Switched to Playfair font");
    } else {
        fontRender.loadFont(interFontData, interFontSize);
        Serial.println("Using Inter font");
    }
}

/**
 * Download image to PSRAM buffer
 */
uint8_t* downloadImage(const String& url, size_t& outLen) {
    Serial.printf("Downloading: %s\n", url.c_str());

    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    http.begin(client, url);
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
    http.setTimeout(30000);

    int httpCode = http.GET();
    if (httpCode != HTTP_CODE_OK) {
        Serial.printf("Download failed: %d\n", httpCode);
        http.end();
        return nullptr;
    }

    int len = http.getSize();
    if (len <= 0 || len > 500000) {
        Serial.println("Invalid size!");
        http.end();
        return nullptr;
    }

    uint8_t* buffer = (uint8_t*)ps_malloc(len);
    if (!buffer) {
        Serial.println("PSRAM alloc failed!");
        http.end();
        return nullptr;
    }

    WiFiClient* stream = http.getStreamPtr();
    size_t bytesRead = stream->readBytes(buffer, len);
    http.end();

    if (bytesRead != len) {
        free(buffer);
        return nullptr;
    }

    outLen = len;
    Serial.printf("Downloaded %d bytes\n", len);
    return buffer;
}

/**
 * Word-wrap text to fit within maxCharsPerLine
 * Returns array of lines (up to maxLines)
 */
int wrapText(const String& text, int maxCharsPerLine, String* outLines, int maxLines) {
    int lineCount = 0;
    int pos = 0;

    while (pos < text.length() && lineCount < maxLines) {
        // Find end of this line
        int remaining = text.length() - pos;
        if (remaining <= maxCharsPerLine) {
            // Rest fits on one line
            outLines[lineCount++] = text.substring(pos);
            break;
        }

        // Find last space within maxCharsPerLine
        int breakPos = pos + maxCharsPerLine;
        while (breakPos > pos && text.charAt(breakPos) != ' ') {
            breakPos--;
        }

        if (breakPos == pos) {
            // No space found, force break at maxCharsPerLine
            breakPos = pos + maxCharsPerLine;
        }

        outLines[lineCount++] = text.substring(pos, breakPos);
        pos = breakPos;

        // Skip the space
        while (pos < text.length() && text.charAt(pos) == ' ') {
            pos++;
        }
    }

    return lineCount;
}

/**
 * Calculate optimal font size and line wrapping to FILL the zone
 * M5GFX uses integer scale factors (1-10+), each unit = 6x8 pixels base
 * Tries different font sizes and picks the largest that fits all text
 */
int calculateOptimalLayout(const String& fullText, int zoneW, int zoneH,
                           String* outLines, int* outLineCount) {
    const int BASE_CHAR_WIDTH = 6;
    const int BASE_CHAR_HEIGHT = 8;

    // Use 60% of zone for conservative margin (prevent text clipping)
    int usableWidth = (zoneW * 60) / 100;
    int usableHeight = (zoneH * 60) / 100;

    int bestFontSize = 2;
    int bestLineCount = 1;
    String bestLines[6];
    bestLines[0] = fullText;

    // Try font sizes from 5 down to 2, find largest that fits
    for (int fontSize = 5; fontSize >= 2; fontSize--) {
        // How many chars fit per line at this font size?
        int charsPerLine = usableWidth / (fontSize * BASE_CHAR_WIDTH);
        if (charsPerLine < 8) continue;  // Too narrow

        // Wrap text to this width
        String tempLines[6];
        int lineCount = wrapText(fullText, charsPerLine, tempLines, 6);

        // Calculate height needed for these lines
        // Height = lineCount * charHeight + (lineCount-1) * spacing
        // charHeight = 8 * fontSize, spacing = 4 * fontSize
        int totalHeight = lineCount * (8 * fontSize) + (lineCount - 1) * (4 * fontSize);

        // Does it fit?
        if (totalHeight <= usableHeight) {
            // This font size works - use it
            bestFontSize = fontSize;
            bestLineCount = lineCount;
            for (int i = 0; i < lineCount; i++) {
                bestLines[i] = tempLines[i];
            }
            break;  // Largest font that fits
        }
    }

    // Copy best result to output
    *outLineCount = bestLineCount;
    for (int i = 0; i < bestLineCount; i++) {
        outLines[i] = bestLines[i];
    }

    Serial.printf("Zone: %dx%d → %d lines, FONT SIZE: %d\n",
                  zoneW, zoneH, bestLineCount, bestFontSize);
    for (int i = 0; i < bestLineCount; i++) {
        Serial.printf("  Line %d: \"%s\" (%d chars)\n", i+1, outLines[i].c_str(), outLines[i].length());
    }

    return bestFontSize;
}

/**
 * Get text width using OpenFontRender
 */
int getTextWidth(const String& text, int fontSize) {
    fontRender.setFontSize(fontSize);
    FT_BBox bbox = fontRender.calculateBoundingBox(0, 0, fontSize, Align::TopLeft, Layout::Horizontal, text.c_str());
    return bbox.xMax - bbox.xMin;
}

/**
 * Word-wrap text for OpenFontRender at a given font size
 * Returns number of lines
 */
int wrapTextForFont(const String& text, int maxWidth, int fontSize, String* outLines, int maxLines) {
    fontRender.setFontSize(fontSize);

    int lineCount = 0;
    int pos = 0;

    while (pos < (int)text.length() && lineCount < maxLines) {
        // Find how much text fits on this line
        int endPos = text.length();
        String testLine = text.substring(pos, endPos);

        // Binary search for the right break point
        while (getTextWidth(testLine, fontSize) > maxWidth && endPos > pos + 1) {
            // Find last space before endPos
            int spacePos = testLine.lastIndexOf(' ');
            if (spacePos > 0) {
                endPos = pos + spacePos;
            } else {
                endPos--;
            }
            testLine = text.substring(pos, endPos);
        }

        outLines[lineCount++] = text.substring(pos, endPos);
        pos = endPos;

        // Skip leading space on next line
        while (pos < (int)text.length() && text.charAt(pos) == ' ') {
            pos++;
        }
    }

    return lineCount;
}

/**
 * Render poem text in the specified zone using OpenFontRender
 * Images are 480x270, displayed at 2x scale (960x540)
 * Uses Inter or Playfair fonts based on poem.town preference
 */
void renderPoemText(int zoneX, int zoneY, int zoneW, int zoneH, const String& strip) {
    // Scale zone coordinates (image is 480x270, display is 960x540)
    int displayX = zoneX * 2;
    int displayY = zoneY * 2;
    int displayW = zoneW * 2;
    int displayH = zoneH * 2;

    // Fallback to strip if no zone
    if (zoneX < 0) {
        displayX = 40;
        displayW = 880;
        if (strip == "top") {
            displayY = 20;
            displayH = 160;
        } else if (strip == "bottom") {
            displayY = 360;
            displayH = 160;
        } else {  // middle
            displayY = 190;
            displayH = 160;
        }
    }

    // Normalize poem text: replace " / " separator with space for re-wrapping
    String fullText = currentPoem;
    fullText.replace(" / ", " ");

    // Use OpenFontRender if fonts are loaded
    if (fontsLoaded) {
        // Set the active font based on poem.town preference
        setActiveFont(currentFont);

        // Use 60% of zone for conservative margin
        int usableWidth = (displayW * 60) / 100;
        int usableHeight = (displayH * 60) / 100;

        // Try font sizes from 56 down to 20, find largest that fits
        int bestFontSize = 20;
        int bestLineCount = 1;
        String bestLines[6];
        bestLines[0] = fullText;

        for (int fontSize = 56; fontSize >= 20; fontSize -= 4) {
            String tempLines[6];
            int lineCount = wrapTextForFont(fullText, usableWidth, fontSize, tempLines, 6);

            // Calculate total height
            int lineHeight = fontSize * 1.3;
            int totalHeight = lineCount * lineHeight;

            if (totalHeight <= usableHeight && lineCount <= 6) {
                bestFontSize = fontSize;
                bestLineCount = lineCount;
                for (int i = 0; i < lineCount; i++) {
                    bestLines[i] = tempLines[i];
                }
                break;
            }
        }

        fontRender.setFontSize(bestFontSize);
        fontRender.setFontColor(TFT_BLACK);

        // Calculate line positions
        int lineHeight = bestFontSize * 1.3;
        int totalTextHeight = bestLineCount * lineHeight;
        int centerX = displayX + displayW / 2;
        int startY = displayY + (displayH - totalTextHeight) / 2 + bestFontSize / 2;

        // Draw each line centered
        for (int i = 0; i < bestLineCount; i++) {
            int lineY = startY + i * lineHeight;
            fontRender.setAlignment(Align::TopCenter);
            fontRender.setCursor(centerX, lineY);
            fontRender.printf("%s", bestLines[i].c_str());
        }

        Serial.printf("Text rendered with %s font, size %d px, %d lines in zone (%d,%d) %dx%d\n",
                      currentFont.c_str(), bestFontSize, bestLineCount, displayX, displayY, displayW, displayH);
        for (int i = 0; i < bestLineCount; i++) {
            Serial.printf("  Line %d: \"%s\"\n", i+1, bestLines[i].c_str());
        }
    } else {
        // Fallback to M5GFX built-in font
        String lines[6];
        int lineCount = 0;
        int fontSize = calculateOptimalLayout(fullText, displayW, displayH, lines, &lineCount);

        display.setTextColor(TFT_BLACK);
        display.setTextDatum(MC_DATUM);
        display.setTextSize(fontSize);

        int charHeight = 8 * fontSize;
        int lineSpacing = 4 * fontSize;
        int totalTextHeight = lineCount * charHeight + (lineCount - 1) * lineSpacing;

        int centerX = displayX + displayW / 2;
        int startY = displayY + (displayH - totalTextHeight) / 2 + charHeight / 2;

        for (int i = 0; i < lineCount; i++) {
            int lineY = startY + i * (charHeight + lineSpacing);
            display.drawString(lines[i], centerX, lineY);
        }

        Serial.printf("Text rendered with builtin font, size %d in zone (%d,%d) %dx%d\n",
                      fontSize, displayX, displayY, displayW, displayH);
    }
}

/**
 * Display clock image with poem overlay
 */
bool displayClockWithPoem(ClockImage* clock) {
    if (!clock) return false;

    // Download image
    size_t imgLen;
    uint8_t* imgBuffer = downloadImage(clock->url, imgLen);
    if (!imgBuffer) return false;

    // Clear display
    display.fillScreen(TFT_WHITE);

    // Draw image (scaled 2x)
    bool success = display.drawPng(imgBuffer, imgLen, 0, 0, 960, 540, 0, 0, 2.0, 2.0);
    free(imgBuffer);

    if (!success) {
        Serial.println("drawPng failed!");
        return false;
    }

    // Overlay poem text
    renderPoemText(clock->zoneX, clock->zoneY, clock->zoneW, clock->zoneH, clock->strip);

    // Update display
    display.display();
    Serial.println("Display updated!");

    return true;
}

/**
 * Draw a simple clock face logo
 */
void drawClockLogo(int centerX, int centerY, int radius) {
    // Draw clock circle
    display.drawCircle(centerX, centerY, radius, TFT_BLACK);
    display.drawCircle(centerX, centerY, radius - 2, TFT_BLACK);

    // Draw hour markers
    for (int i = 0; i < 12; i++) {
        float angle = i * 30 * PI / 180 - PI/2;
        int innerR = radius - 15;
        int outerR = radius - 5;
        int x1 = centerX + cos(angle) * innerR;
        int y1 = centerY + sin(angle) * innerR;
        int x2 = centerX + cos(angle) * outerR;
        int y2 = centerY + sin(angle) * outerR;
        display.drawLine(x1, y1, x2, y2, TFT_BLACK);
    }

    // Draw stopped hands at 4:25
    // Hour hand: 4 hours + 25/60 adjustment = 4.417 * 30 = 132.5 degrees
    float hourAngle = (4 + 25.0/60.0) * 30 * PI / 180 - PI/2;
    int hourLen = radius * 0.5;
    display.drawLine(centerX, centerY,
                     centerX + cos(hourAngle) * hourLen,
                     centerY + sin(hourAngle) * hourLen, TFT_BLACK);

    // Minute hand: 25 minutes = 25 * 6 = 150 degrees
    float minAngle = 25 * 6 * PI / 180 - PI/2;
    int minLen = radius * 0.7;
    display.drawLine(centerX, centerY,
                     centerX + cos(minAngle) * minLen,
                     centerY + sin(minAngle) * minLen, TFT_BLACK);

    // Center dot
    display.fillCircle(centerX, centerY, 4, TFT_BLACK);
}

/**
 * Display status message with Poem/1:Stopped Clocks Mod branding
 */
void displayStatus(const char* status) {
    display.fillScreen(TFT_WHITE);

    // Draw clock logo in background (semi-faded)
    drawClockLogo(480, 270, 180);

    // Title: Poem/1:Stopped Clocks Mod
    display.setTextColor(TFT_BLACK);
    display.setTextDatum(MC_DATUM);
    display.setTextSize(4);
    display.drawString("Poem/1", 480, 180);
    display.setTextSize(2);
    display.drawString("Stopped Clocks Mod", 480, 240);

    // Status message
    display.setTextSize(2);
    display.drawString(status, 480, 380);

    display.display();
}

/**
 * Display error message with Poem/1:Stopped Clocks Mod branding
 */
void displayError(const char* message) {
    display.fillScreen(TFT_WHITE);

    // Draw clock logo in background
    drawClockLogo(480, 270, 180);

    // Title
    display.setTextColor(TFT_BLACK);
    display.setTextDatum(MC_DATUM);
    display.setTextSize(4);
    display.drawString("Poem/1", 480, 180);
    display.setTextSize(2);
    display.drawString("Stopped Clocks Mod", 480, 240);

    // Error message
    display.setTextSize(2);
    display.setTextColor(TFT_BLACK);
    display.drawString(message, 480, 380);

    display.display();
}

/**
 * Main update cycle
 */
void updateDisplay() {
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) {
        Serial.println("Failed to get time");
        return;
    }

    int timeCode12 = to12HourFormat(timeinfo.tm_hour, timeinfo.tm_min);
    String time24 = getCurrentTime24();

    // Check if minute changed
    if (timeCode12 == lastDisplayedTime) {
        return;
    }

    Serial.printf("\n=== Time: %s (12h: %04d) ===\n", time24.c_str(), timeCode12);

    // Fetch poem from poem.town
    if (!fetchPoem(time24)) {
        Serial.println("Failed to fetch poem, using placeholder");
        currentPoem = "Time moves on / But clocks stand still";
    }

    // Find matching clock image
    ClockImage* clock = findClockImage(timeCode12);
    if (!clock) {
        Serial.println("No clock image found!");
        return;
    }

    // Display clock with poem
    if (displayClockWithPoem(clock)) {
        lastDisplayedTime = timeCode12;
    }
}

void setup() {
    Serial.begin(115200);
    unsigned long start = millis();
    while (!Serial && (millis() - start) < 3000) delay(10);

    Serial.println("\n\n=== Poem/1: Stopped Clocks Mod ===");
    Serial.printf("PSRAM: %d bytes free\n", ESP.getFreePsram());

    // Initialize power pin
    pinMode(GPIO_NUM_44, OUTPUT);
    digitalWrite(GPIO_NUM_44, LOW);

    // Initialize display
    Serial.println("Initializing display...");
    display.init();
    Serial.printf("Display: %d x %d\n", display.width(), display.height());

    // Seed random
    randomSeed(analogRead(0) + millis());

    // Connect WiFi
    displayStatus("Connecting to WiFi...");
    if (!connectWiFi()) {
        displayError("WiFi failed");
        return;
    }

    // Sync time
    displayStatus("Syncing time...");
    if (!syncTime()) {
        displayError("NTP sync failed");
        return;
    }

    // Register with poem.town
    displayStatus("Registering device...");
    registerWithPoemTown();

    // Load fonts (Inter and Playfair)
    displayStatus("Loading fonts...");
    if (!loadFonts()) {
        Serial.println("Font loading failed, using builtin font");
        // Continue without custom fonts
    }

    // Fetch clock index
    displayStatus("Loading clock index...");
    if (!fetchClockIndex()) {
        displayError("Index load failed");
        return;
    }

    // Initial display
    updateDisplay();

    Serial.println("\n=== Poem/1 ready ===");
}

void loop() {
    // Check every 10 seconds
    static unsigned long lastCheck = 0;
    unsigned long now = millis();

    if (now - lastCheck >= 10000) {
        lastCheck = now;
        updateDisplay();
    }

    // Status log every minute
    static int idleCount = 0;
    if (++idleCount % 60 == 0) {
        struct tm timeinfo;
        if (getLocalTime(&timeinfo)) {
            Serial.printf("Time: %02d:%02d | Heap: %d | PSRAM: %d\n",
                          timeinfo.tm_hour, timeinfo.tm_min,
                          ESP.getFreeHeap(), ESP.getFreePsram());
        }
    }
    delay(1000);
}
