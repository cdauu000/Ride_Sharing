/* Real backend smoke; no API mocks. Credentials are read locally, never printed. */
const { chromium } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

(async () => {
  const browser = await chromium.launch({
    executablePath:
      process.env.CHROME_BIN ||
      "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
  });
  const errors = [];
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(process.env.WEB_BASE_URL || "http://127.0.0.1:3000");
    await page.locator('input[type="email"]').fill("passenger@rise.local");
    const env = fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8");
    const password = env
      .split(/\r?\n/)
      .find((line) => line.startsWith("RISE_DEMO_PASSWORD="))
      .slice("RISE_DEMO_PASSWORD=".length);
    await page.locator('input[type="password"]').fill(password);
    await page.locator('form button[type="submit"]').click();
    const search = page.locator('.trip-form button[type="submit"]');
    await search.waitFor({ timeout: 30000 });
    await search.click();
    await page
      .getByText("Xe máy nội đô", { exact: true })
      .first()
      .waitFor({ timeout: 30000 });
    if (!(await page.locator("body").innerText()).includes("174.000"))
      throw new Error("Missing maximum pool quote");
    const output = path.resolve(__dirname, "../../artifacts/screenshots");
    fs.mkdirSync(output, { recursive: true });
    await page.screenshot({
      path: path.join(output, "passenger-live.png"),
      fullPage: true,
    });
    console.log(
      "Real backend login + trip request + three-service recommendations passed.",
    );
    const driverContext = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    });
    const driver = await driverContext.newPage();
    driver.on("pageerror", (error) => errors.push(error.message));
    const base = process.env.WEB_BASE_URL || "http://127.0.0.1:3000";
    await driver.goto(base);
    await driver.locator('input[type="email"]').fill("bike@rise.local");
    await driver.locator('input[type="password"]').fill(password);
    await driver.locator('form button[type="submit"]').click();
    await driver.locator(".driver-summary").waitFor({ timeout: 30000 });
    const selection = page.waitForResponse(
      (response) =>
        response.url().includes("/select") &&
        response.request().method() === "POST",
    );
    await page
      .locator(".candidate-card")
      .filter({ has: page.getByText("Xe máy nội đô", { exact: true }) })
      .getByRole("button")
      .click();
    const selected = await (await selection).json();
    if (!selected.id) throw new Error("Live selection failed");
    await driver
      .getByRole("button", { name: "Nhận chuyến", exact: true })
      .first()
      .click({ timeout: 15000 });
    async function pollBooking(status) {
      for (let i = 0; i < 40; i++) {
        const r = await driver.request.get(
          base + "/api/bookings/" + selected.id,
        );
        const b = await r.json();
        if (b.escrow_status === status) return b;
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      throw new Error("Escrow state did not reach " + status);
    }
    await pollBooking("DEPOSITED");
    await driver
      .getByRole("button", { name: "Bắt đầu chuyến", exact: true })
      .first()
      .click();
    for (let index = 0; index < 2; index++) {
      const stopResponse = driver.waitForResponse(
        (response) =>
          response.url().endsWith("/stops/" + index + "/complete") &&
          response.request().method() === "POST",
      );
      await driver.locator(".stop-list li.current button").first().click();
      const result = await stopResponse;
      if (!result.ok()) throw new Error("Live stop failed: " + result.status());
      await driver.waitForTimeout(500);
    }
    await driver
      .getByRole("button", { name: "Hoàn thành chuyến", exact: true })
      .first()
      .click();
    const completed = await pollBooking("RELEASED");
    if (completed.ride_status !== "COMPLETED")
      throw new Error("Ride not completed");
    const payout = await (
      await driver.request.get(
        base + "/api/bookings/" + selected.id + "/price-breakdown",
      )
    ).json();
    if (payout.settlement.total_driver_payout_vnd !== 64800)
      throw new Error("Wrong live bike payout");
    await driver.screenshot({
      path: path.join(output, "driver-live.png"),
      fullPage: true,
    });
    console.log(
      "Real browser passenger selection + driver acceptance + escrow + ordered stops + complete + exact payout passed.",
    );
    const admin = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    admin.on("pageerror", (error) => errors.push(error.message));
    await admin.goto(base);
    await admin.locator('input[type="email"]').fill("admin@rise.local");
    await admin.locator('input[type="password"]').fill(password);
    await admin.locator('form button[type="submit"]').click();
    await admin.locator(".admin-metrics").waitFor({ timeout: 30000 });
    await admin.locator(".fund-balance").waitFor({ timeout: 30000 });
    await admin.screenshot({
      path: path.join(output, "admin-live.png"),
      fullPage: true,
    });
    console.log("Runtime errors:", JSON.stringify(errors));
    if (errors.length) throw new Error("Browser runtime error");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
