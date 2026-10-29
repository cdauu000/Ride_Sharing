/* Live Photon + FOSSGIS verification, local app only; creates no trip/booking. */
const { chromium, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const base = "http://127.0.0.1:3020";
const out = path.resolve(
  process.env.ROUTE_TEST_OUTPUT || "../artifacts/maps/route-live-v1",
);
assert.ok(
  !fs.existsSync(path.join(out, "results.json")),
  "Use a new evidence version",
);
const password = fs
  .readFileSync(path.join(__dirname, "../../.env"), "utf8")
  .split(/\r?\n/)
  .find((line) => line.startsWith("RISE_DEMO_PASSWORD="))
  .slice(19);

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1050 },
    locale: "vi-VN",
    timezoneId: "Asia/Ho_Chi_Minh",
  });
  const errors = [],
    chosen = [],
    routing = [];
  let forbiddenMutations = 0;
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (request) => {
    if (
      /\/api\/(trip-requests|bookings)(\/|$)/.test(
        new URL(request.url()).pathname,
      ) &&
      request.method() !== "GET"
    )
      forbiddenMutations++;
  });
  page.on("response", async (response) => {
    if (
      response.url().endsWith("/api/locations/route") &&
      response.status() === 200
    ) {
      try {
        routing.push({
          request: response.request().postDataJSON(),
          body: await response.json(),
        });
      } catch {}
    }
  });
  try {
    await page.goto(base);
    await page
      .getByLabel("Email", { exact: true })
      .fill("passenger@rise.local");
    await page.getByLabel("Mật khẩu", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
    for (const [label, query, select] of [
      [
        "Điểm đón",
        "144 Xuân Thủy, Hà Nội",
        (item) => item.kind === "address" && item.label.includes("144"),
      ],
      [
        "Điểm đến",
        "Jacal Hotel 138 Phùng Hưng",
        (item) => item.id === "local-jacayl-phung-hung-138",
      ],
    ]) {
      await page
        .getByRole("combobox", { name: label, exact: true })
        .fill(query);
      const responsePromise = page.waitForResponse((r) =>
        r.url().endsWith("/api/locations/search"),
      );
      await page
        .getByRole("button", {
          name: `Tìm địa chỉ ${label.toLowerCase()}`,
          exact: true,
        })
        .click();
      const response = await responsePromise;
      assert.equal(response.status(), 200);
      const result = (await response.json()).items.find(select);
      assert.ok(result, `No matching address for ${query}`);
      chosen.push(result);
      await page
        .getByRole("option", {
          name: new RegExp(result.label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
        })
        .click();
    }
    const summary = page.getByLabel("Tổng quãng đường", { exact: true });
    await expect(summary.locator("strong")).toContainText("km", {
      timeout: 45000,
    });
    await expect
      .poll(
        () => routing.some((r) => r.request.dropoff.lat === chosen[1].lat),
        { timeout: 10000 },
      )
      .toBe(true);
    const live = routing.findLast(
      (r) => r.request.dropoff.lat === chosen[1].lat,
    );
    assert.equal(live.body.profile, "car");
    assert.ok(
      live.body.distance_m > 0 && live.body.geometry.coordinates.length > 2,
    );
    await expect(summary.locator("strong")).toHaveText(
      (live.body.distance_m / 1000).toLocaleString("vi-VN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }) + " km",
    );
    await expect(page.locator(".road-route-line")).toHaveCount(1);
    await expect(page.locator(".address-reference")).toContainText(
      "chưa xác minh cổng đón",
    );
    const anchorErrors = await page.evaluate(() =>
      [...document.querySelectorAll(".map-pin")].map((marker, i) => {
        const box = marker.getBoundingClientRect(),
          line = document.querySelectorAll(".road-connector")[i];
        const point = line.getPointAtLength(0),
          p = new DOMPoint(point.x, point.y).matrixTransform(
            line.getScreenCTM(),
          );
        return Math.hypot(box.x + 18 - p.x, box.y + 42 - p.y);
      }),
    );
    assert.ok(
      anchorErrors.every((value) => value < 2),
      "Pin tip and raw coordinate differ",
    );
    await expect
      .poll(
        () =>
          page
            .locator(".leaflet-tile-pane img")
            .evaluateAll(
              (imgs) =>
                imgs.filter((img) => img.complete && img.naturalWidth > 0)
                  .length,
            ),
        { timeout: 20000 },
      )
      .toBeGreaterThan(0);
    await page
      .locator(".planner-layout")
      .screenshot({ path: path.join(out, "desktop.png") });
    const aliases = [];
    for (const query of [
      "Jacal Hotel",
      "Jacayl Hotel Hà Đông",
      "138 Phùng Hưng Hà Nội",
    ]) {
      const response = await page.request.post(base + "/api/locations/search", {
        data: { query },
      });
      assert.equal(response.status(), 200);
      const item = (await response.json()).items[0];
      assert.equal(item.id, chosen[1].id);
      aliases.push({ query, id: item.id });
    }
    await page.setViewportSize({ width: 375, height: 900 });
    await expect
      .poll(() =>
        page
          .locator(".sidebar")
          .evaluate((element) => element.getBoundingClientRect().right),
      )
      .toBeLessThanOrEqual(0);
    await expect(summary.locator("strong")).toContainText("km");
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    await page.locator(".planner-map").scrollIntoViewIfNeeded();
    await expect
      .poll(
        () =>
          page
            .locator(".leaflet-tile-pane img")
            .evaluateAll(
              (images) =>
                images.length > 0 &&
                images.every(
                  (image) => image.complete && image.naturalWidth > 0,
                ),
            ),
        { timeout: 20000 },
      )
      .toBe(true);
    await expect
      .poll(() =>
        page
          .locator(".leaflet-tile-pane img")
          .evaluateAll(
            (images) =>
              images.filter((image) => image.complete && image.naturalWidth > 0)
                .length,
          ),
      )
      .toBeGreaterThan(0);
    await page
      .locator(".planner-map")
      .screenshot({ path: path.join(out, "mobile.png") });
    await page
      .getByRole("combobox", { name: "Điểm đến", exact: true })
      .fill("Địa chỉ mới đang nhập");
    await expect(summary).not.toContainText(" km");
    await expect(page.locator(".road-route-line")).toHaveCount(0);
    assert.deepEqual(errors, []);
    assert.equal(forbiddenMutations, 0);
    const report = {
      status: "PASS",
      checkedAt: new Date().toISOString(),
      chosen,
      route: live,
      anchorErrors,
      aliases,
      errors,
      tripOrBookingMutations: forbiddenMutations,
    };
    fs.writeFileSync(
      path.join(out, "results.json"),
      JSON.stringify(report, null, 2),
    );
    console.log(
      JSON.stringify({
        status: report.status,
        distance_m: live.body.distance_m,
        duration_s: live.body.duration_s,
        geometryPoints: live.body.geometry.coordinates.length,
        anchorErrors,
        aliases: aliases.length,
        errors,
        tripOrBookingMutations: forbiddenMutations,
        output: out,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
