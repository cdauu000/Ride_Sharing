/* Real public-address searches through the local UI/API; creates no booking. */
const { chromium, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const base = process.env.ADDRESS_TEST_BASE_URL || "http://127.0.0.1:3020";
assert.equal(new URL(base).hostname, "127.0.0.1");
const out = path.resolve(
  process.env.ADDRESS_TEST_OUTPUT || "../artifacts/address-search/live-v1",
);
assert.ok(
  !fs.existsSync(path.join(out, "results.json")),
  "Use a new output version",
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
    accessibility = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.goto(base);
    await page
      .getByLabel("Email", { exact: true })
      .fill("passenger@rise.local");
    await page.getByLabel("Mật khẩu", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
    for (const [label, query, number] of [
      ["Điểm đón", "144 Xuân Thủy, Hà Nội", "144"],
      ["Điểm đến", "1 Đại Cồ Việt, Hà Nội", "1"],
    ]) {
      const input = page.getByRole("combobox", { name: label, exact: true });
      await input.fill(query);
      let response;
      for (let attempt = 0; attempt < 2; attempt++) {
        const pending = page.waitForResponse(
          (r) =>
            r.url().endsWith("/api/locations/search") &&
            r.request().method() === "POST",
        );
        pending.catch(() => {});
        if (!attempt)
          await page
            .getByRole("button", {
              name: `Tìm địa chỉ ${label.toLowerCase()}`,
              exact: true,
            })
            .click();
        else {
          const field = page.locator(".place-field").filter({ has: input });
          const retry = field.getByRole("button", {
            name: "Thử lại",
            exact: true,
          });
          await expect(retry).toBeEnabled({ timeout: 15000 });
          await retry.click();
        }
        response = await pending;
        if (response.status() !== 429) break;
      }
      assert.equal(response.status(), 200);
      const body = await response.json();
      const result = body.items.find(
        (item) => item.kind === "address" && item.label.includes(number),
      );
      assert.ok(result, `No house address returned for ${query}`);
      const option = page.getByRole("option", {
        name: result.label + " Có số nhà · Kiểm tra ghim trước khi đặt",
        exact: true,
      });
      await expect(option).toBeVisible();
      if (process.env.ADDRESS_TEST_AXE_PATH) {
        await page.addScriptTag({ path: process.env.ADDRESS_TEST_AXE_PATH });
        const audit = await page.evaluate(async () => {
          const result = await window.axe.run(
            document.querySelector(".trip-form"),
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
        accessibility.push({ field: label, ...audit });
        fs.writeFileSync(
          path.join(out, "accessibility.json"),
          JSON.stringify(accessibility, null, 2),
        );
        assert.equal(
          audit.violations.length,
          0,
          "Address form accessibility violations; see accessibility.json",
        );
      }
      await page.screenshot({
        path: path.join(
          out,
          label === "Điểm đón"
            ? "pickup-results.png"
            : "destination-results.png",
        ),
        fullPage: true,
      });
      await option.click();
      await expect(input).toHaveValue(result.label);
      await expect(
        page.getByLabel(`${label}: vĩ độ`, { exact: true }),
      ).toHaveValue(String(result.lat));
      chosen.push({ field: label, query, selected: result });
      await page.waitForTimeout(1200); // Keep public-service requests modest.
    }
    const pendingTrip = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/trip-requests") &&
        r.request().method() === "POST",
    );
    pendingTrip.catch(() => {});
    await page
      .getByRole("button", { name: "Tìm chuyến phù hợp", exact: true })
      .click();
    const trip = await pendingTrip;
    assert.equal(trip.status(), 201);
    const payload = trip.request().postDataJSON();
    for (const [index, key] of ["pickup", "dropoff"].entries()) {
      assert.deepEqual(payload[key], {
        lat: chosen[index].selected.lat,
        lon: chosen[index].selected.lon,
      });
      assert.equal(payload[`${key}_label`], chosen[index].selected.label);
    }
    const request = await trip.json();
    await expect(page.locator(".recommendations-section")).toContainText(
      /Tìm cách đi phù hợp/,
    );
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
        { timeout: 30000 },
      )
      .toBe(true);
    await page.locator(".planner-layout").screenshot({
      path: path.join(out, "selected-addresses.png"),
    });
    await page.setViewportSize({ width: 375, height: 900 });
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      )
      .toBe(true);
    assert.equal(errors.length, 0);
    fs.writeFileSync(
      path.join(out, "results.json"),
      JSON.stringify(
        {
          mode: "REAL_UI_REAL_API_REAL_PHOTON",
          chosen,
          request_id: request.id,
          payload,
          mobile_no_overflow: true,
          runtimeErrors: errors,
          accessibility,
          bookings_created: 0,
        },
        null,
        2,
      ),
    );
    console.log(
      JSON.stringify({
        passed: true,
        resolved_addresses: chosen.length,
        trip_request_status: trip.status(),
        bookings_created: 0,
        runtime_errors: errors.length,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.message.replaceAll(password, "[REDACTED]"));
  process.exitCode = 1;
});
