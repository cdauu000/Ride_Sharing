import { expect, test, type Page } from "@playwright/test";

const pickup = {
  id: "pickup-result",
  lat: 21.03881,
  lon: 105.78189,
  label: "144 Xuân Thủy, Cầu Giấy, Hà Nội",
  kind: "address",
};
const dropoff = {
  id: "dropoff-result",
  lat: 21.0061,
  lon: 105.8431,
  label: "1 Đại Cồ Việt, Hai Bà Trưng, Hà Nội",
  kind: "address",
};

async function setup(page: Page, failSearch = false) {
  const queries: string[] = [],
    trips: Record<string, unknown>[] = [],
    errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route(/^https:\/\/tile\.openstreetmap\.(org|de)\//, (route) =>
    route.abort(),
  );
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    let body: unknown = [];
    if (path === "/api/auth/me")
      body = { id: "address-tester", name: "Khách", role: "PASSENGER" };
    if (path === "/api/system")
      body = { routing_mode: "fixture", escrow_mode: "local" };
    if (path === "/api/locations/search") {
      const query = request.postDataJSON().query;
      queries.push(query);
      if (failSearch)
        return route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: { code: "GEOCODER_UNAVAILABLE" } }),
        });
      body = { items: [query.includes("144") ? pickup : dropoff] };
    }
    if (path === "/api/trip-requests") {
      trips.push(request.postDataJSON());
      body = {
        id: "address-request",
        mode: "URBAN",
        allowed_service_codes: ["CAR_URBAN_PRIVATE"],
        rejection_reasons: {},
      };
    }
    if (path.endsWith("/recommendations"))
      body = { run_id: "address-run", items: [] };
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await page.goto("/");
  return { queries, trips, errors };
}

test("specific pickup and destination addresses supply chosen coordinates and labels", async ({
  page,
}) => {
  const recorded = await setup(page);
  await page
    .getByRole("combobox", { name: "Điểm đón", exact: true })
    .fill("144 Xuân Thủy Hà Nội");
  expect(recorded.queries).toHaveLength(0);
  await page
    .getByRole("button", { name: "Tìm địa chỉ điểm đón", exact: true })
    .click();
  await page.getByRole("option", { name: /144 Xuân Thủy/ }).click();
  await page
    .getByRole("combobox", { name: "Điểm đến", exact: true })
    .fill("1 Đại Cồ Việt Hà Nội");
  await page
    .getByRole("button", { name: "Tìm địa chỉ điểm đến", exact: true })
    .click();
  await page.getByRole("option", { name: /1 Đại Cồ Việt/ }).click();
  await expect(page.getByLabel("Điểm đón: vĩ độ", { exact: true })).toHaveValue(
    String(pickup.lat),
  );
  await expect(
    page.getByLabel("Điểm đến: kinh độ", { exact: true }),
  ).toHaveValue(String(dropoff.lon));
  await page.getByRole("button", { name: /Tìm chuyến phù hợp/ }).click();
  await expect.poll(() => recorded.trips.length).toBe(1);
  expect(recorded.trips[0]).toMatchObject({
    pickup: { lat: pickup.lat, lon: pickup.lon },
    dropoff: { lat: dropoff.lat, lon: dropoff.lon },
    pickup_label: pickup.label,
    dropoff_label: dropoff.label,
  });
  const swap = page.getByRole("button", {
    name: "Đổi điểm đón và điểm đến",
    exact: true,
  });
  const a = await swap.boundingBox(),
    b = await page
      .getByRole("button", { name: "Tìm địa chỉ điểm đón", exact: true })
      .boundingBox();
  expect(
    a &&
      b &&
      a.x < b.x + b.width &&
      b.x < a.x + a.width &&
      a.y < b.y + b.height &&
      b.y < a.y + a.height,
  ).toBe(false);
  await swap.click();
  await expect(
    page.getByRole("combobox", { name: "Điểm đón", exact: true }),
  ).toHaveValue(dropoff.label);
  await expect(page.getByLabel("Điểm đón: vĩ độ", { exact: true })).toHaveValue(
    String(dropoff.lat),
  );
  await expect(
    page.getByRole("combobox", { name: "Điểm đến", exact: true }),
  ).toHaveValue(pickup.label);
  expect(recorded.errors).toEqual([]);
});

test("unavailable address search keeps typed text and blocks using the previous location", async ({
  page,
}) => {
  const recorded = await setup(page, true);
  const input = page.getByRole("combobox", { name: "Điểm đến", exact: true });
  await input.fill("1 Đại Cồ Việt Hà Nội");
  await page
    .getByRole("button", { name: "Tìm địa chỉ điểm đến", exact: true })
    .click();
  await expect(page.locator(".place-field .notice")).toContainText(
    "Chưa kết nối được dịch vụ tìm địa chỉ",
  );
  await expect(input).toHaveValue("1 Đại Cồ Việt Hà Nội");
  await page.getByRole("button", { name: /Tìm chuyến phù hợp/ }).click();
  await expect(page.locator(".trip-form > .notice")).toContainText(
    "tìm và chọn địa chỉ",
  );
  expect(recorded.trips).toHaveLength(0);
  expect(recorded.errors).toEqual([]);
});

test("manual house address requires confirming the selected map pin", async ({
  page,
}) => {
  const recorded = await setup(page);
  await page
    .getByRole("combobox", { name: "Điểm đón", exact: true })
    .fill("Số 7 ngõ nhỏ, Hà Đông");
  await page
    .getByRole("button", {
      name: "Gắn địa chỉ đã nhập với ghim hiện tại",
      exact: true,
    })
    .click();
  expect(recorded.trips).toHaveLength(0);
  await page
    .getByRole("button", { name: "Xác nhận địa chỉ tại ghim này", exact: true })
    .click();
  await page.getByRole("button", { name: /Tìm chuyến phù hợp/ }).click();
  await expect.poll(() => recorded.trips.length).toBe(1);
  expect(recorded.trips[0]).toMatchObject({
    pickup_label: "Số 7 ngõ nhỏ, Hà Đông",
    pickup: { lat: 20.961, lon: 105.747 },
  });
  expect(recorded.queries).toHaveLength(0);
  expect(recorded.errors).toEqual([]);
});
