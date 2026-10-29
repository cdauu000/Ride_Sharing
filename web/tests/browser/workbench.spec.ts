import { expect, test, type Page } from "@playwright/test";
const { selectSamplePlace } = require("../address-helper.cjs");

type ApiRecord = {
  path: string;
  method: string;
  body: Record<string, unknown>;
  key: string | undefined;
};

const runtimeErrors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  runtimeErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(async ({ page }) => {
  expect(runtimeErrors.get(page) ?? []).toEqual([]);
});

async function mockApi(page: Page, role = "PASSENGER") {
  const requests: ApiRecord[] = [];
  let booked = false;
  const booking = {
    id: "booking-12345678",
    service_code: "CAR_URBAN_POOL",
    ride_status: "HELD",
    price_status: "QUOTED",
    escrow_status: "NONE",
    quoted_price_cap_vnd: 174000,
    current_estimated_price_vnd: 143000,
  };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api", "");
    const method = request.method();
    const body =
      method === "GET"
        ? {}
        : (request.postDataJSON() as Record<string, unknown>);
    requests.push({
      path,
      method,
      body,
      key: request.headers()["idempotency-key"],
    });
    let payload: unknown = [];
    if (path === "/system")
      payload = { routing_mode: "fixture", escrow_mode: "local" };
    else if (path === "/auth/me")
      payload = {
        id: "user-1",
        email: "test@example.com",
        name: "Nguyễn An",
        role,
      };
    else if (path === "/trip-requests")
      payload = {
        id: "request-1",
        mode: "URBAN",
        allowed_service_codes: [
          "BIKE_URBAN",
          "CAR_URBAN_PRIVATE",
          "CAR_URBAN_POOL",
        ],
        rejection_reasons: {},
      };
    else if (path.endsWith("/recommendations"))
      payload = {
        run_id: "run-1",
        items: [
          {
            id: "pool-1",
            service_code: "CAR_URBAN_POOL",
            price: 143000,
            quote: 155000,
            unmatched: 174000,
            matched_estimate: 143000,
            pickup_eta_min: 8,
            duration_min: 52,
            p_match_label: "Cao",
            labels: ["Tiết kiệm"],
          },
          {
            id: "bike-1",
            service_code: "BIKE_URBAN",
            price: 81000,
            pickup_eta_min: 5,
            duration_min: 35,
            labels: ["Rẻ nhất", "Nhanh nhất"],
          },
          {
            id: "private-1",
            service_code: "CAR_URBAN_PRIVATE",
            price: 194000,
            pickup_eta_min: 7,
            duration_min: 40,
          },
        ],
      };
    else if (path.endsWith("/select")) {
      booked = true;
      payload = booking;
    } else if (path === "/bookings") payload = booked ? [booking] : [];
    else if (path === "/driver/settings")
      payload = {
        online: true,
        kyc_status: "VERIFIED",
        vehicle_type: "CAR4",
        accepts_urban: true,
        pool_enabled: true,
        accepts_intercity: true,
      };
    else if (path === "/driver/earnings")
      payload = {
        total_driver_payout_vnd: 155200,
        guarantee_total_vnd: 7300,
        payouts: [],
      };
    else if (path === "/offers")
      payload = [
        {
          id: "offer-1",
          booking_id: "booking-offer-1",
          service_code: "CAR_URBAN_PRIVATE",
          status: "PENDING",
          expires_at: new Date(Date.now() + 18000).toISOString(),
        },
      ];
    else if (path === "/admin/metrics")
      payload = { trip_requests: 8, bookings: 5, completed: 2 };
    else if (path === "/admin/fund")
      payload = {
        balance_vnd: 4992700,
        onchain_balance_vnd: null,
        p_actual_booking: null,
        p_star_booking: null,
        p_star_ride: null,
        ledger: [
          {
            id: "seed",
            entry_type: "INITIAL_SEED",
            amount_signed_vnd: 5000000,
            balance_after_vnd: 5000000,
            created_at: "2026-10-27T08:00:00Z",
          },
          {
            id: "guarantee",
            entry_type: "GUARANTEE_PAYOUT",
            amount_signed_vnd: -7300,
            balance_after_vnd: 4992700,
            created_at: "2026-10-27T09:00:00Z",
            booking_id: "b-1",
          },
        ],
      };
    else if (path === "/admin/users")
      payload = [
        {
          id: "driver-1",
          name: "Tài xế kiểm thử",
          email: "driver@example.com",
          role: "DRIVER",
          kyc_status: "PENDING",
        },
      ];
    else if (path === "/admin/batch-runs")
      payload = [
        { id: "batch-1", solver_status: "OPTIMAL", assigned: 2, requests: 7 },
      ];
    else if (path === "/admin/jobs")
      payload = [
        {
          id: "job-1",
          job_type: "ESCROW_COMMAND",
          run_at: Date.now() / 1000,
          status: "DEAD_LETTER",
          attempts: 5,
          max_attempts: 5,
        },
      ];
    else if (path === "/admin/surveys")
      payload = { total_responses: 0, student_count: 0, worker_count: 0 };
    else if (method !== "GET") payload = { success: true };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
  // The UI remains usable when external map tiles cannot be loaded.
  await page.route(/^https:\/\/tile\.openstreetmap\.(org|de)\//, (route) =>
    route.abort(),
  );
  return requests;
}

test("passenger sees all price obligations before placing an idempotent booking", async ({
  page,
}) => {
  const requests = await mockApi(page);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Đi theo cách của bạn." }),
  ).toBeVisible();
  await expect(
    page.getByText(/Ký quỹ sổ cái cục bộ, chưa có giao dịch testnet/),
  ).toBeVisible();
  await page.getByRole("button", { name: /Tìm chuyến phù hợp/ }).click();
  const pool = page
    .locator("article.candidate-card")
    .filter({ hasText: "Taxi ghép nội đô" });
  await expect(pool.getByText("143.000 đ")).toBeVisible();
  await expect(pool.getByText("155.000 đ")).toBeVisible();
  await expect(pool.getByText("174.000 đ")).toBeVisible();
  await pool.getByRole("button", { name: "Chọn chuyến" }).click();
  await expect(page.getByText("Ký quỹ mức trần")).toBeVisible();
  await expect(page.getByText("Đang chờ tài xế").first()).toBeVisible();
  const selection = requests.find((request) =>
    request.path.endsWith("/select"),
  );
  expect(selection?.body).toEqual({ candidate_id: "pool-1" });
  expect(selection?.key).toMatch(/^[0-9a-f-]{36}$/i);
  expect(pageErrors).toEqual([]);
});

test("driver can accept an offer with the canonical API contract", async ({
  page,
}) => {
  const requests = await mockApi(page, "DRIVER");
  await page.goto("/");
  await page.getByRole("button", { name: "Dành cho tài xế" }).click();
  await expect(
    page.getByRole("heading", { name: "Lời mời nhận chuyến" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Nhận chuyến", exact: true }).click();
  await expect
    .poll(
      () =>
        requests.filter((request) => request.path === "/offers/offer-1/accept")
          .length,
    )
    .toBe(1);
  expect(
    requests.find((request) => request.path === "/offers/offer-1/accept")?.key,
  ).toMatch(/^[0-9a-f-]{36}$/i);
});

test("admin financial figures and KYC actions come from the API", async ({
  page,
}) => {
  const requests = await mockApi(page, "ADMIN");
  await page.goto("/");
  await page.getByRole("button", { name: "Quản trị vận hành" }).click();
  await expect(
    page.getByRole("heading", { name: "Một hệ thống, mọi hành trình" }),
  ).toBeVisible();
  await expect(page.getByText("4.992.700 đ").first()).toBeVisible();
  await expect(page.getByText("Chưa có bằng chứng đối soát")).toBeVisible();
  await page.getByRole("button", { name: "Duyệt Tài xế kiểm thử" }).click();
  await expect
    .poll(
      () =>
        requests.filter(
          (request) => request.path === "/admin/drivers/driver-1/kyc-review",
        ).length,
    )
    .toBe(1);
  expect(
    requests.find(
      (request) => request.path === "/admin/drivers/driver-1/kyc-review",
    )?.body,
  ).toEqual({ status: "VERIFIED" });
  const batchRow = page.getByRole("row").filter({ hasText: "batch-1" });
  await expect(
    batchRow.getByRole("cell", { name: "OPTIMAL", exact: true }),
  ).toBeVisible();
  await expect(
    batchRow.getByRole("cell", { name: "2", exact: true }),
  ).toBeVisible();
  await expect(
    batchRow.getByRole("cell", { name: "7", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect
    .poll(
      () => requests.filter((r) => r.path === "/admin/jobs/job-1/retry").length,
    )
    .toBe(1);
  expect(
    requests.find((r) => r.path === "/admin/jobs/job-1/retry")?.key,
  ).toMatch(/^[0-9a-f-]{36}$/i);
});

test("mobile planning has no horizontal overflow and keeps navigation reachable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: /Tìm chuyến phù hợp/ }),
  ).toBeVisible();
  await expect(page.getByText(/Chưa tải được nền bản đồ/)).toBeVisible();
  await page.getByRole("button", { name: "Mở điều hướng" }).click();
  await page.getByRole("button", { name: "Hành trình của tôi" }).click();
  await expect(
    page.getByRole("heading", { name: "Từ xác nhận đến điểm đến" }),
  ).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
});

test("editing the route clears the old menu even when the next search is throttled", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: /Tìm chuyến phù hợp/ }).click();
  await expect(page.locator("article.candidate-card")).toHaveCount(3);
  await selectSamplePlace(page, "Điểm đến", "4");
  await expect(page.locator("article.candidate-card")).toHaveCount(0);
  await page.route("**/api/trip-requests", (route) =>
    route.fulfill({
      status: 429,
      headers: { "Retry-After": "5" },
      contentType: "application/json",
      body: JSON.stringify({ detail: { code: "RATE_LIMITED" } }),
    }),
  );
  await page.getByRole("button", { name: /Tìm chuyến phù hợp/ }).click();
  await expect(page.locator(".notice[role=alert]")).toContainText(
    "Vui lòng chờ",
  );
  await expect(page.locator(".notice[role=alert]")).toContainText(
    /Thử lại sau \d+ giây/,
  );
  await expect(page.locator("article.candidate-card")).toHaveCount(0);
});

test("driver settings wait for loading and retain edits during background refresh", async ({
  page,
}) => {
  await mockApi(page, "DRIVER");
  let ready!: () => void;
  const gate = new Promise<void>((resolve) => {
    ready = resolve;
  });
  let reads = 0;
  await page.route("**/api/driver/settings", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    reads += 1;
    if (reads === 1) await gate;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        online: true,
        kyc_status: "VERIFIED",
        vehicle_type: "CAR4",
        pool_enabled: true,
        accepts_urban: true,
        accepts_intercity: true,
        max_driver_detour_km: 10 + reads,
      }),
    });
  });
  await page.goto("/");
  await expect(page.getByText("Đang tải cấu hình nhận chuyến…")).toBeVisible();
  const online = page.getByRole("checkbox", { name: /Trực tuyến/ });
  await expect(online).toHaveCount(0);
  ready();
  await expect(online).toBeChecked();
  await online.uncheck();
  await expect(page.getByText("Bạn có thay đổi chưa lưu.")).toBeVisible();
  // SWR intentionally deduplicates reconnects for two seconds after a read.
  await page.waitForTimeout(2100);
  await page.evaluate(() => {
    window.dispatchEvent(new Event("offline"));
    window.dispatchEvent(new Event("online"));
  });
  await expect.poll(() => reads).toBeGreaterThan(1);
  await expect(online).not.toBeChecked();
});
