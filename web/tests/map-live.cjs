/* Live visual verification: actual map tiles, local API, no request mocks. */
const { chromium, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

const base = process.env.MAP_TEST_BASE_URL || "http://127.0.0.1:3020";
assert.equal(new URL(base).hostname, "127.0.0.1");
const output = path.resolve(
  process.env.MAP_TEST_OUTPUT || "../artifacts/maps/map-display-v1",
);
assert.ok(
  !fs.existsSync(path.join(output, "results.json")),
  "Use a new output version",
);
const password = fs
  .readFileSync(path.join(__dirname, "../../.env"), "utf8")
  .split(/\r?\n/)
  .find((line) => line.startsWith("RISE_DEMO_PASSWORD="))
  .slice(19);

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1050 },
    locale: "vi-VN",
    timezoneId: "Asia/Ho_Chi_Minh",
  });
  const runtimeErrors = [],
    serverErrors = [];
  page.on("pageerror", (error) =>
    runtimeErrors.push(error.message.replaceAll(password, "[REDACTED]")),
  );
  page.on("response", (response) => {
    if (response.url().startsWith(base + "/api/") && response.status() >= 500)
      serverErrors.push({
        path: new URL(response.url()).pathname,
        status: response.status(),
      });
  });
  try {
    await page.goto(base);
    await page
      .getByLabel("Email", { exact: true })
      .fill("passenger@rise.local");
    await page.getByLabel("Mật khẩu", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
    await expect(page.locator(".leaflet-container")).toBeVisible();
    await expect
      .poll(
        async () =>
          page
            .locator(".leaflet-tile-pane img")
            .evaluateAll(
              (images) =>
                images.length > 0 &&
                images.every(
                  (image) => image.complete && image.naturalWidth === 256,
                ),
            ),
        { timeout: 30000 },
      )
      .toBe(true);
    await expect(page.getByLabel("Nền bản đồ", { exact: true })).toHaveValue(
      "osm-de",
    );
    await expect(page.locator(".map-tile-warning")).toHaveCount(0);
    await expect(page.locator(".map-pin")).toHaveCount(2);
    const attribution = await page
      .locator(".leaflet-control-attribution")
      .innerText();
    assert.ok(
      attribution.includes("OpenStreetMap") && attribution.includes("FOSSGIS"),
    );
    await page.screenshot({
      path: path.join(output, "map-live.png"),
      fullPage: true,
      mask: [page.locator('input[type="password"]')],
    });
    const tiles = await page
      .locator(".leaflet-tile-pane img")
      .evaluateAll((images) =>
        images.map((image) => ({
          url: image.src,
          loaded: image.complete && image.naturalWidth > 0,
          width: image.naturalWidth,
          height: image.naturalHeight,
        })),
      );
    await page.setViewportSize({ width: 375, height: 900 });
    await expect
      .poll(() =>
        page
          .locator(".sidebar")
          .evaluate((element) =>
            Math.round(element.getBoundingClientRect().right),
          ),
      )
      .toBeLessThanOrEqual(0);
    await page.locator(".leaflet-container").scrollIntoViewIfNeeded();
    await page
      .getByRole("button", { name: "Xem toàn bộ hành trình", exact: true })
      .click();
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      )
      .toBe(true);
    await expect
      .poll(
        () =>
          page
            .locator(".leaflet-tile-pane img")
            .evaluateAll(
              (images) =>
                images.length > 0 &&
                images.every(
                  (image) => image.complete && image.naturalWidth === 256,
                ),
            ),
        { timeout: 30000 },
      )
      .toBe(true);
    await page.screenshot({
      path: path.join(output, "map-mobile.png"),
      fullPage: false,
    });
    const axePath = process.env.MAP_TEST_AXE_PATH;
    let accessibility = null;
    if (axePath) {
      await page.addScriptTag({ path: axePath });
      accessibility = await page.evaluate(async () => {
        const result = await window.axe.run(
          document.querySelector(".planner-map"),
          {
            runOnly: {
              type: "tag",
              values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
            },
          },
        );
        return {
          violations: result.violations.map((item) => ({
            id: item.id,
            impact: item.impact,
            nodes: item.nodes.map((node) => ({
              target: node.target,
              failureSummary: node.failureSummary,
            })),
          })),
          incomplete: result.incomplete.map((item) => ({
            id: item.id,
            nodes: item.nodes.length,
          })),
        };
      });
      fs.writeFileSync(
        path.join(output, "accessibility.json"),
        JSON.stringify(accessibility, null, 2),
      );
      assert.equal(
        accessibility.violations.length,
        0,
        "Map accessibility violations; see accessibility.json",
      );
    }
    assert.equal(runtimeErrors.length, 0);
    assert.equal(serverErrors.length, 0);
    const results = {
      mode: "REAL_TILES_REAL_LOCAL_API",
      base,
      provider: "osm-de",
      tiles,
      attribution,
      markers: 2,
      mobile_no_overflow: true,
      accessibility,
      runtimeErrors,
      serverErrors,
      checked_at: new Date().toISOString(),
    };
    fs.writeFileSync(
      path.join(output, "results.json"),
      JSON.stringify(results, null, 2),
    );
    console.log(
      JSON.stringify({
        passed: true,
        loaded_tiles: tiles.filter((tile) => tile.loaded).length,
        runtime_errors: runtimeErrors.length,
        server_errors: serverErrors.length,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.message.replaceAll(password, "[REDACTED]"));
  process.exitCode = 1;
});
