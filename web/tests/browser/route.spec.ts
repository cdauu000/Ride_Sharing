import { expect, test, type Page } from "@playwright/test";

async function setup(page: Page, failure = false, busy = false) {
  const requests: {
    pickup: { lat: number; lon: number };
    dropoff: { lat: number; lon: number };
  }[] = [];
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route(/^https:\/\/tile\.openstreetmap\.(de|org)\//, (route) =>
    route.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#e8efdc"/></svg>',
    }),
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = [];
    if (path === "/api/auth/me")
      body = { id: "route-test", name: "Khách", role: "PASSENGER" };
    if (path === "/api/system")
      body = { routing_mode: "fixture", escrow_mode: "local" };
    if (path === "/api/locations/search")
      body = {
        items: [
          {
            id: "jacayl",
            lat: 20.968238,
            lon: 105.786924,
            label: "Jacayl Hotel – Hà Đông, 138 Phùng Hưng, Phúc La, Hà Nội",
            kind: "address",
            precision: "reference",
          },
        ],
      };
    if (path === "/api/locations/route") {
      const data = route.request().postDataJSON();
      requests.push(data);
      if (failure || (busy && requests.length === 1))
        return route.fulfill({
          status: failure ? 503 : 429,
          headers: { "Retry-After": "1" },
          contentType: "application/json",
          body: JSON.stringify({
            detail: {
              code: failure
                ? "ROUTE_PREVIEW_UNAVAILABLE"
                : "ROUTE_PREVIEW_BUSY",
            },
          }),
        });
      const a = [data.pickup.lon, data.pickup.lat],
        b = [data.dropoff.lon, data.dropoff.lat];
      body = {
        distance_m: requests.length === 1 ? 9291 : 12345,
        duration_s: 890.2,
        geometry: {
          type: "LineString",
          coordinates: [a, [(a[0] + b[0]) / 2, a[1]], b],
        },
        waypoints: [
          { location: a, distance_m: 0 },
          { location: b, distance_m: 0 },
        ],
        profile: "car",
        attribution: "OSRM",
      };
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto("/");
  return { requests, errors };
}

test("road kilometers, geometry and exact marker tip update with selected addresses", async ({
  page,
}) => {
  const recorded = await setup(page);
  const summary = page.getByLabel("Tổng quãng đường", { exact: true });
  await expect(summary).toContainText("9,29 km");
  await expect(page.locator(".road-route-line")).toHaveCount(1);
  const difference = await page.evaluate(() => {
    const marker = document.querySelector(".map-pin")!.getBoundingClientRect();
    const path = document.querySelector(".road-route-line") as SVGPathElement;
    const p = path.getPointAtLength(0),
      matrix = path.getScreenCTM()!;
    const screen = new DOMPoint(p.x, p.y).matrixTransform(matrix);
    return Math.hypot(marker.x + 18 - screen.x, marker.y + 42 - screen.y);
  });
  expect(difference).toBeLessThan(2);
  await page
    .getByRole("combobox", { name: "Điểm đến", exact: true })
    .fill("Jacal Hotel 138 Phùng Hưng");
  await expect(summary).not.toContainText("9,29 km");
  await expect(page.locator(".road-route-line")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Tìm địa chỉ điểm đến", exact: true })
    .click();
  await page.getByRole("option", { name: /Jacayl Hotel/ }).click();
  await expect(summary).toContainText("12,35 km");
  await expect(page.locator(".address-reference")).toContainText(
    "chưa xác minh cổng đón",
  );
  expect(recorded.requests.at(-1)?.dropoff).toEqual({
    lat: 20.968238,
    lon: 105.786924,
  });
  await page
    .getByRole("button", { name: "Đổi điểm đón và điểm đến", exact: true })
    .click();
  await expect.poll(() => recorded.requests.at(-1)?.pickup.lat).toBe(20.968238);
  expect(recorded.errors).toEqual([]);
});

test("dragging pickup A changes pickup even while destination is selected", async ({
  page,
}) => {
  const recorded = await setup(page);
  await expect(page.getByLabel("Tổng quãng đường")).toContainText("9,29 km");
  await page.getByRole("combobox", { name: "Điểm đến", exact: true }).focus();
  const initialDestination = await page
    .getByLabel("Điểm đến: vĩ độ", { exact: true })
    .inputValue();
  const pin = page.locator(".map-pin").first(),
    box = await pin.boundingBox();
  await page.mouse.move(box!.x + 18, box!.y + 18);
  await page.mouse.down();
  await page.mouse.move(box!.x + 85, box!.y - 25, { steps: 12 });
  await page.mouse.up();
  await expect(
    page.getByLabel("Điểm đón: vĩ độ", { exact: true }),
  ).not.toHaveValue("20.961");
  await expect(page.getByLabel("Điểm đến: vĩ độ", { exact: true })).toHaveValue(
    initialDestination,
  );
  await expect.poll(() => recorded.requests.length).toBeGreaterThan(1);
  expect(recorded.errors).toEqual([]);
});

test("routing outage shows retry and never presents a fixture distance", async ({
  page,
}) => {
  const recorded = await setup(page, true);
  await expect(page.getByLabel("Tổng quãng đường")).toContainText(
    "Chưa kết nối được dịch vụ tính đường bộ",
  );
  await expect(page.locator(".road-route-line")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Tính lại quãng đường", exact: true }),
  ).toBeVisible();
  expect(recorded.errors).toEqual([]);
});

test("routing waits and retries when the shared provider quota is occupied", async ({
  page,
}) => {
  const recorded = await setup(page, false, true);
  await expect(page.getByLabel("Tổng quãng đường")).toContainText("12,35 km", {
    timeout: 10000,
  });
  expect(recorded.requests).toHaveLength(2);
  expect(recorded.errors).toEqual([]);
});
