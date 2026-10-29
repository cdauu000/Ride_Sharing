import { expect, test, type Page } from "@playwright/test";
const { selectSamplePlace } = require("../address-helper.cjs");

// Only these tests use synthetic image tiles; live verification uses real maps.
const tile =
  '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e8efdc"/><path d="M0 64H256M64 0V256" stroke="#fff" stroke-width="12"/><text x="12" y="130">TEST TILE</text></svg>';
const sources = /^https:\/\/tile\.openstreetmap\.(org|de)\//;
const runtimeErrors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  runtimeErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(async ({ page }) => {
  expect(runtimeErrors.get(page) ?? []).toEqual([]);
});

async function openPlanning(page: Page) {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const data =
      path === "/api/auth/me"
        ? { id: "map-test", name: "Khách kiểm thử", role: "PASSENGER" }
        : path === "/api/system"
          ? { routing_mode: "fixture", escrow_mode: "local" }
          : [];
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  await page.goto("/");
  await expect(page.locator(".leaflet-container")).toBeVisible();
}

async function loadedTiles(page: Page): Promise<number> {
  return page
    .locator(".leaflet-tile-pane img")
    .evaluateAll(
      (images) =>
        images.filter(
          (image) =>
            (image as HTMLImageElement).complete &&
            (image as HTMLImageElement).naturalWidth > 0,
        ).length,
    );
}

test("a failed image does not remove the rest of the basemap or its attribution", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let requested = 0;
  await page.route(sources, (route) =>
    ++requested === 1
      ? route.abort()
      : route.fulfill({ contentType: "image/svg+xml", body: tile }),
  );
  await openPlanning(page);
  await expect.poll(() => loadedTiles(page)).toBeGreaterThan(0);
  await expect(page.getByLabel("Nền bản đồ", { exact: true })).toHaveValue(
    "osm-de",
  );
  await expect(page.locator(".leaflet-control-attribution")).toContainText(
    "FOSSGIS",
  );
  await expect(page.locator(".map-pin")).toHaveCount(2);
  expect(errors).toEqual([]);
});

test("switches to the other provider when the entire primary basemap fails", async ({
  page,
}) => {
  await page.route(sources, (route) =>
    route.request().url().includes(".de/")
      ? route.abort()
      : route.fulfill({ contentType: "image/svg+xml", body: tile }),
  );
  await openPlanning(page);
  await expect(page.getByLabel("Nền bản đồ", { exact: true })).toHaveValue(
    "osm",
  );
  await expect.poll(() => loadedTiles(page)).toBeGreaterThan(0);
  await expect(page.locator(".leaflet-control-attribution")).toContainText(
    "OpenStreetMap contributors",
  );
  await expect(page.locator(".map-tile-warning")).toHaveCount(0);
});

test("retry restores real tile elements after a total connection failure", async ({
  page,
}) => {
  let connected = false;
  await page.route(sources, (route) =>
    connected
      ? route.fulfill({ contentType: "image/svg+xml", body: tile })
      : route.abort(),
  );
  await openPlanning(page);
  await expect(page.locator(".map-tile-warning")).toContainText(
    "Chưa tải được nền bản đồ",
  );
  connected = true;
  await page
    .getByRole("button", { name: "Tải lại bản đồ", exact: true })
    .click();
  await expect.poll(() => loadedTiles(page)).toBeGreaterThan(0);
  await expect(page.locator(".map-tile-warning")).toHaveCount(0);
  await expect(page.locator(".map-pin")).toHaveCount(2);
});

test("clicking the visible map changes the selected destination", async ({
  page,
}) => {
  await page.route(sources, (route) =>
    route.fulfill({ contentType: "image/svg+xml", body: tile }),
  );
  await openPlanning(page);
  await expect.poll(() => loadedTiles(page)).toBeGreaterThan(0);
  await page.getByLabel("Điểm đến", { exact: true }).focus();
  const longitude = page.getByLabel("Điểm đến: kinh độ", { exact: true });
  const previous = await longitude.inputValue();
  const map = page.locator(".leaflet-container"),
    box = await map.boundingBox();
  expect(box).not.toBeNull();
  await map.click({ position: { x: box!.width * 0.75, y: box!.height * 0.7 } });
  await expect(longitude).not.toHaveValue(previous);
  await expect(page.locator(".map-pin")).toHaveCount(2);
});

test("changing providers releases old map listeners before changing the route", async ({
  page,
}) => {
  await page.route(sources, (route) =>
    route.fulfill({ contentType: "image/svg+xml", body: tile }),
  );
  await openPlanning(page);
  for (const provider of ["osm", "osm-de", "osm"]) {
    await page.getByLabel("Nền bản đồ", { exact: true }).selectOption(provider);
    await expect.poll(() => loadedTiles(page)).toBeGreaterThan(0);
    for (const place of ["4", "1"]) {
      await selectSamplePlace(page, "Điểm đến", place);
      await expect.poll(() => loadedTiles(page)).toBeGreaterThan(0);
      await expect(page.locator(".map-pin")).toHaveCount(2);
    }
  }
});
