/* User acceptance: real UI and API, isolated local test data, no route mocks. */
const { chromium, expect } = require("@playwright/test");
const { selectSamplePlace } = require("./address-helper.cjs");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

const base = process.env.UAT_BASE_URL || "http://127.0.0.1:3020";
const out = path.resolve(
  process.env.UAT_OUTPUT || "../artifacts/acceptance/uat-20261028-01",
);
assert.equal(new URL(base).hostname, "127.0.0.1");
const password = fs
  .readFileSync(path.resolve(__dirname, "../../.env"), "utf8")
  .split(/\r?\n/)
  .find((line) => line.startsWith("RISE_DEMO_PASSWORD="))
  .slice(19);
const results = [],
  findings = [],
  runtimeErrors = [],
  network = [],
  consoleErrors = [];
const sessions = {},
  state = {};
const selectedCases = process.env.UAT_CASES
  ? new Set(process.env.UAT_CASES.split(","))
  : null;
const names = {
  BIKE_URBAN: "Xe máy nội đô",
  CAR_URBAN_PRIVATE: "Taxi bao xe",
  CAR_URBAN_POOL: "Taxi ghép nội đô",
  CAR_INTERCITY_PRIVATE: "Bao xe liên tỉnh",
  CAR_INTERCITY_POOL: "Ghép xe liên tỉnh",
};
let browser;
let activeCase;
const redact = (value) =>
  String(value)
    .replaceAll(password, "[REDACTED]")
    .replace(/\/(shared|share)\/[A-Za-z0-9_-]+/g, "/$1/[REDACTED]");
async function screenshot(page, name) {
  const file = `screenshots/${name}.png`;
  await page.screenshot({
    path: path.join(out, file),
    fullPage: true,
    mask: [page.locator('input[type="password"]'), page.locator(".share-box")],
  });
  return file;
}
function save() {
  fs.writeFileSync(
    path.join(out, "results.json"),
    JSON.stringify(
      {
        date: "2026-10-28",
        base,
        mode: "REAL_BROWSER_REAL_API_LOCAL_FIXTURE",
        results,
        findings,
        runtimeErrors,
        network,
        consoleErrors,
      },
      null,
      2,
    ),
  );
}
async function test(id, title, fn, deps = []) {
  if (selectedCases && !selectedCases.has(id)) return;
  deps = deps.filter((dep) => !selectedCases || selectedCases.has(dep));
  if (
    deps.some(
      (dep) => !results.some((r) => r.id === dep && r.status === "PASS"),
    )
  ) {
    results.push({
      id,
      title,
      status: "BLOCKED",
      reason: "Prerequisite case failed",
      deps,
    });
    save();
    return;
  }
  const started = Date.now();
  activeCase = id;
  try {
    const detail = (await fn()) || {};
    const evidence = detail.page
      ? await screenshot(detail.page, id)
      : undefined;
    delete detail.page;
    results.push({
      id,
      title,
      status: "PASS",
      duration_ms: Date.now() - started,
      evidence,
      ...detail,
    });
    console.log(`${id} PASS ${title}`);
  } catch (error) {
    results.push({
      id,
      title,
      status: "FAIL",
      duration_ms: Date.now() - started,
      error: redact(error.message),
    });
    for (const [slug, session] of Object.entries(sessions)) {
      if (!session.page.isClosed())
        await screenshot(session.page, `${id}-failure-${slug}`).catch(() => {});
    }
    console.log(`${id} FAIL ${redact(error.message).slice(0, 400)}`);
  }
  save();
}
async function newPage(actor, viewport = { width: 1440, height: 1000 }) {
  const context = await browser.newContext({
    viewport,
    locale: "vi-VN",
    timezoneId: "Asia/Ho_Chi_Minh",
  });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  page.on("pageerror", (e) =>
    runtimeErrors.push({ actor, message: redact(e.message) }),
  );
  page.on("console", (msg) => {
    if (msg.type() === "error")
      consoleErrors.push({ actor, message: redact(msg.text()).slice(0, 400) });
  });
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 400)
      network.push({
        actor,
        case_id: activeCase,
        at: new Date().toISOString(),
        path: redact(new URL(r.url()).pathname),
        status: r.status(),
      });
  });
  await page.goto(base, { timeout: 60000 });
  return { context, page };
}
async function login(slug) {
  const session = await newPage(slug),
    p = session.page;
  await p.getByLabel("Email", { exact: true }).fill(slug + "@rise.local");
  await p.getByLabel("Mật khẩu", { exact: true }).fill(password);
  const r = await action(p, "/auth/login", () =>
    p.getByRole("button", { name: "Đăng nhập", exact: true }).click(),
  );
  assert.equal(r.status, 200);
  session.user = r.body;
  await p.locator(".sidebar-user").waitFor();
  sessions[slug] = session;
  return p;
}
async function action(p, suffix, click, method = "POST") {
  const pending = p.waitForResponse(
    (r) =>
      new URL(r.url()).pathname.endsWith(suffix) &&
      r.request().method() === method,
    { timeout: 20000 },
  );
  pending.catch(() => {});
  await click();
  const r = await pending;
  return { status: r.status(), body: await r.json() };
}
async function data(p, url) {
  const r = await p.request.get(base + "/api" + url);
  assert.equal(r.status(), 200, `Read ${url}: ${r.status()}`);
  return r.json();
}
async function poll(p, url, predicate) {
  let last;
  for (let n = 0; n < 80; n++) {
    last = await data(p, url);
    if (predicate(last)) return last;
    await p.waitForTimeout(250);
  }
  throw new Error(`Timed out ${url}: ${JSON.stringify(last).slice(0, 350)}`);
}
async function nav(p, label) {
  await p
    .getByRole("navigation")
    .getByRole("button", { name: label, exact: true })
    .click();
}
async function online(p, value) {
  await p.getByRole("checkbox", { name: /Trực tuyến/ }).setChecked(value);
  const r = await action(
    p,
    "/driver/settings",
    () => p.getByRole("button", { name: "Lưu cấu hình", exact: true }).click(),
    "PUT",
  );
  assert.equal(r.status, 200);
  return r;
}
async function search(p, options = {}) {
  await nav(p, "Tìm chuyến");
  await selectSamplePlace(p, "Điểm đón", options.from ?? 0);
  await selectSamplePlace(p, "Điểm đến", options.to ?? 1);
  await p.getByLabel("Số hành khách").selectOption(String(options.seats ?? 1));
  await p.getByLabel("Phương tiện").selectOption(options.vehicle ?? "ANY");
  await p
    .getByLabel("Ngân sách mong muốn", { exact: true })
    .fill(String(options.min ?? 50000));
  await p
    .getByLabel("Tối đa có thể trả", { exact: true })
    .fill(String(options.max ?? 800000));
  await p
    .getByLabel("Hành lý lớn", { exact: true })
    .setChecked(Boolean(options.luggage));
  await p.getByLabel("Trời đang mưa", { exact: true }).setChecked(false);
  if (options.departure) {
    await p.getByRole("button", { name: "Hẹn trước", exact: true }).click();
    await p
      .getByLabel("Ngày và giờ đi", { exact: true })
      .fill(localTime(options.departure));
    await p.getByLabel("Có thể đón sớm (phút)").fill("30");
    await p.getByLabel("Có thể đón muộn (phút)").fill("30");
  } else await p.getByRole("button", { name: "Đi ngay", exact: true }).click();
  const pending = p.waitForResponse(
    (r) =>
      /\/trip-requests\/[^/]+\/recommendations$/.test(
        new URL(r.url()).pathname,
      ) && r.request().method() === "GET",
  );
  await p
    .getByRole("button", { name: "Tìm chuyến phù hợp", exact: true })
    .click();
  const r = await pending;
  assert.equal(r.status(), 200);
  const menu = await r.json();
  if (menu.items.length) await p.locator(".candidate-card").first().waitFor();
  return menu;
}
async function select(p, service) {
  const card = p
    .locator(".candidate-card")
    .filter({
      has: p.getByRole("heading", { name: names[service], exact: true }),
    })
    .first();
  const r = await action(p, "/select", () =>
    card.getByRole("button", { name: "Chọn chuyến", exact: true }).click(),
  );
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.ok(r.body.id);
  return r.body;
}
function bookingCard(p, b) {
  return p.locator(".booking-card").filter({ hasText: b.id.slice(0, 8) });
}
function rideCard(p, b) {
  return p
    .locator(".ride-card")
    .filter({ hasText: (b.ride_plan_id || b.scheduled_trip_id).slice(0, 8) });
}
function driverFor(b) {
  return Object.values(sessions).find((s) => s.user?.id === b.driver_id)?.page;
}
async function accept(b) {
  const p = driverFor(b);
  assert.ok(p, "Assigned driver session exists");
  await p.getByLabel("Vĩ độ", { exact: true }).fill("20.961");
  await p.getByLabel("Kinh độ", { exact: true }).fill("105.747");
  const gps = await action(
    p,
    "/driver/location",
    () =>
      p.getByRole("button", { name: "Cập nhật vị trí", exact: true }).click(),
    "PUT",
  );
  assert.equal(gps.status, 200);
  const card = p.locator(".offer-card").filter({ hasText: b.id.slice(0, 8) });
  await card.waitFor();
  const r = await action(p, `/offers/${b.offer_id}/accept`, () =>
    card.getByRole("button", { name: "Nhận chuyến", exact: true }).click(),
  );
  assert.equal(r.status, 200, JSON.stringify(r.body));
  return poll(p, `/bookings/${b.id}`, (v) => v.escrow_status === "DEPOSITED");
}
async function cancel(p, b) {
  const card = bookingCard(p, b);
  await card.getByRole("button", { name: "Hủy chuyến", exact: true }).click();
  const r = await action(p, `/bookings/${b.id}/cancel`, () =>
    card
      .getByRole("button", { name: "Xác nhận hủy chuyến", exact: true })
      .click(),
  );
  assert.equal(r.status, 200, JSON.stringify(r.body));
  return r.body;
}
async function finish(p, b) {
  const id = b.ride_plan_id || b.scheduled_trip_id,
    card = rideCard(p, b);
  await card.waitFor();
  const plans = await data(p, "/driver/rides");
  const current = plans.find((x) => x.id === id);
  assert.ok(current);
  const total = current.stops.length;
  await expect(card.locator(".stop-list li")).toHaveCount(total, {
    timeout: 15000,
  });
  const start = await action(p, `/rides/${id}/start`, () =>
    card.getByRole("button", { name: "Bắt đầu chuyến", exact: true }).click(),
  );
  assert.equal(start.status, 200, JSON.stringify(start.body));
  assert.ok(total > 0);
  for (let n = 0; n < total; n++) {
    const button = card.locator(".stop-list li.current button");
    await expect(button).toBeEnabled();
    const r = await action(p, `/rides/${id}/stops/${n}/complete`, () =>
      button.click(),
    );
    assert.equal(r.status, 200, JSON.stringify(r.body));
  }
  const r = await action(p, `/rides/${id}/complete`, () =>
    card
      .getByRole("button", { name: "Hoàn thành chuyến", exact: true })
      .click(),
  );
  assert.equal(r.status, 200, JSON.stringify(r.body));
  return poll(
    p,
    `/bookings/${b.id}/price-breakdown`,
    (v) => v.escrow?.status === "RELEASED",
  );
}
function localTime(value) {
  return new Date(new Date(value).getTime() + 7 * 3600000)
    .toISOString()
    .slice(0, 16);
}
async function advance(seconds) {
  const p = sessions.admin.page;
  await nav(p, "Quản trị vận hành");
  await p.getByLabel("Tiến đồng hồ (giây)").fill(String(seconds));
  const r = await action(p, "/admin/demo-clock", () =>
    p.getByRole("button", { name: "Tiến thời gian demo", exact: true }).click(),
  );
  assert.equal(r.status, 200);
  const run = await action(p, "/admin/jobs/run", () =>
    p
      .getByRole("button", { name: "Chạy các job đến hạn", exact: true })
      .click(),
  );
  assert.equal(run.status, 200);
  await nav(p, "Tìm chuyến");
  return r.body;
}
async function publish(departure) {
  const p = sessions.driver.page;
  await p
    .locator(".publish-form")
    .getByLabel("Ngày, giờ khởi hành")
    .fill(localTime(departure));
  const r = await action(p, "/driver/pool-trips", () =>
    p.getByRole("button", { name: "Đăng chuyến", exact: true }).click(),
  );
  assert.equal(r.status, 201, JSON.stringify(r.body));
  return r.body;
}

(async () => {
  fs.mkdirSync(path.join(out, "screenshots"), { recursive: true });
  browser = await chromium.launch({
    executablePath:
      process.env.CHROME_BIN ||
      "C:/Program Files/Google/Chrome/Application/chrome.exe",
    headless: true,
  });
  try {
    await test("UAT-01", "Khởi động và đăng nhập đúng vai trò", async () => {
      for (const slug of [
        "passenger",
        "passenger2",
        "bike",
        "driver",
        "admin",
        "driver2",
        "driver3",
      ])
        await login(slug);
      for (const slug of ["driver2", "driver3"]) {
        await online(sessions[slug].page, false);
        await sessions[slug].context.close();
      }
      await nav(sessions.admin.page, "Tìm chuyến");
      if (
        selectedCases &&
        !selectedCases.has("UAT-08") &&
        !selectedCases.has("UAT-26")
      )
        await sessions.bike.context.close();
      const system = await data(sessions.passenger.page, "/system");
      assert.equal(system.routing_mode, "fixture");
      assert.equal(system.escrow_mode, "local");
      state.system = system;
      return {
        page: sessions.passenger.page,
        observed:
          "7 tài khoản đúng vai trò; hai tài xế phụ tắt nhận chuyến qua UI để kiểm soát cung",
        system,
      };
    });
    await test(
      "UAT-02",
      "Đăng nhập sai mật khẩu bị từ chối",
      async () => {
        const s = await newPage("invalid-login"),
          p = s.page;
        await p
          .getByLabel("Email", { exact: true })
          .fill("passenger@rise.local");
        await p
          .getByLabel("Mật khẩu", { exact: true })
          .fill("Incorrect-password-123");
        const r = await action(p, "/auth/login", () =>
          p.getByRole("button", { name: "Đăng nhập", exact: true }).click(),
        );
        assert.equal(r.status, 401);
        await expect(p.locator(".notice.error")).toBeVisible();
        const evidence = await screenshot(p, "UAT-02");
        await s.context.close();
        return {
          evidence,
          observed: "Không đăng nhập được; có thông báo lỗi",
          response_code: r.body.detail?.code,
        };
      },
      ["UAT-01"],
    );
    await test(
      "UAT-03",
      "Đăng ký hành khách mới trên giao diện",
      async () => {
        const s = await newPage("register"),
          p = s.page;
        await p
          .getByRole("button", { name: "Chưa có tài khoản? Đăng ký" })
          .click();
        await p
          .getByLabel("Họ và tên", { exact: true })
          .fill("Hành khách nghiệm thu");
        await p
          .getByLabel("Email", { exact: true })
          .fill(`uat-${Date.now()}@example.test`);
        await p.getByLabel("Mật khẩu").fill(password);
        await p.getByLabel("Loại tài khoản").selectOption("PASSENGER");
        const r = await action(p, "/auth/register", () =>
          p.getByRole("button", { name: "Tạo tài khoản", exact: true }).click(),
        );
        assert.equal(r.status, 201, JSON.stringify(r.body));
        await p.locator(".sidebar-user").waitFor();
        const evidence = await screenshot(p, "UAT-03");
        await s.context.close();
        return {
          evidence,
          observed: "Tạo tài khoản và vào màn hình tìm chuyến",
        };
      },
      ["UAT-01"],
    );
    await test(
      "UAT-04",
      "Kiểm tra lỗi ngân sách và điểm đón trùng điểm đến",
      async () => {
        const p = sessions.passenger.page;
        await p.getByLabel("Ngân sách mong muốn").fill("900000");
        await p.getByLabel("Tối đa có thể trả").fill("800000");
        await p
          .getByRole("button", { name: "Tìm chuyến phù hợp", exact: true })
          .click();
        await expect(p.locator(".notice.error")).toContainText(
          "Ngân sách mong muốn",
        );
        await p.getByLabel("Ngân sách mong muốn").fill("50000");
        await selectSamplePlace(p, "Điểm đến", "0");
        await p
          .getByRole("button", { name: "Tìm chuyến phù hợp", exact: true })
          .click();
        await expect(p.locator(".notice.error")).toContainText(
          "Điểm đón và điểm đến cần khác nhau",
        );
        return {
          page: p,
          observed: "Chặn hai đầu vào sai và hiển thị tiếng Việt",
        };
      },
      ["UAT-01"],
    );
    await test(
      "UAT-05",
      "Tìm chuyến, xem đủ ba dịch vụ và ba mức giá Pool",
      async () => {
        const p = sessions.passenger.page,
          menu = await search(p);
        assert.deepEqual(
          new Set(menu.items.map((x) => x.service_code)),
          new Set(["BIKE_URBAN", "CAR_URBAN_PRIVATE", "CAR_URBAN_POOL"]),
        );
        const text = await p.locator(".recommendation-grid").innerText();
        for (const money of ["81.000", "194.000", "155.000", "174.000"])
          assert.ok(text.includes(money), money);
        return {
          page: p,
          observed:
            "Xe máy 81.000; bao xe 194.000; Pool báo dự kiến, trần ghép 155.000 và không ghép 174.000",
          candidate_count: menu.items.length,
        };
      },
      ["UAT-01"],
    );
    await test(
      "UAT-06",
      "Hành lý lớn và hai hành khách loại xe máy",
      async () => {
        const p = sessions.passenger.page;
        for (const options of [{ luggage: true }, { seats: 2 }]) {
          const m = await search(p, options);
          assert.ok(m.items.length);
          assert.ok(m.items.every((x) => x.service_code !== "BIKE_URBAN"));
        }
        return {
          page: p,
          observed: "Cả hai trường hợp chỉ còn phương án taxi",
        };
      },
      ["UAT-01"],
    );
    await test(
      "UAT-07",
      "Hủy khi tài xế chưa nhận, không phát sinh tiền",
      async () => {
        const p = sessions.passenger.page;
        await search(p);
        const b = await select(p, "BIKE_URBAN");
        assert.equal(b.ride_status, "HELD");
        const cancelled = await cancel(p, b);
        assert.equal(cancelled.ride_status, "CANCELLED_BY_PASSENGER");
        assert.equal(cancelled.cancellation_fee_vnd, 0);
        const detail = await data(p, `/bookings/${b.id}/price-breakdown`);
        assert.equal(detail.escrow, null);
        assert.equal(detail.settlement, null);
        assert.equal(cancelled.escrow_status, "NONE");
        return {
          page: p,
          observed: "Hủy HELD, phí 0, chưa tạo ký quỹ",
          booking_id: b.id,
          escrow_status: cancelled.escrow_status,
        };
      },
      ["UAT-05"],
    );
    await test(
      "UAT-08",
      "Đặt xe máy và tài xế nhận offer thật",
      async () => {
        const p = sessions.passenger.page;
        await search(p);
        state.bike = await select(p, "BIKE_URBAN");
        await accept(state.bike);
        const card = rideCard(sessions.bike.page, state.bike);
        await expect(
          card.locator(".stop-list li.current button"),
        ).toBeDisabled();
        return {
          page: sessions.bike.page,
          observed:
            "Offer được nhận, ký quỹ DEPOSITED; chưa bắt đầu thì không xác nhận điểm đón",
          booking_id: state.bike.id,
        };
      },
      ["UAT-07"],
    );
    await test(
      "UAT-09",
      "Chia sẻ hành trình và SOS mô phỏng",
      async () => {
        const p = sessions.passenger.page,
          b = state.bike,
          card = bookingCard(p, b);
        const share = await action(p, `/bookings/${b.id}/share-link`, () =>
          card.getByRole("button", { name: "Chia sẻ", exact: true }).click(),
        );
        assert.equal(share.status, 200);
        const popupPromise = p.waitForEvent("popup");
        await card.getByRole("link", { name: "Mở liên kết" }).click();
        const popup = await popupPromise;
        await popup.waitForLoadState("domcontentloaded");
        await expect(popup.locator("body")).toContainText(
          /CHIA SẺ HÀNH TRÌNH/i,
        );
        await screenshot(popup, "UAT-09-public-share");
        await popup.close();
        await nav(p, "Hành trình của tôi");
        const sos = await action(p, `/bookings/${b.id}/sos`, () =>
          card
            .getByRole("button", { name: "SOS mô phỏng", exact: true })
            .click(),
        );
        assert.equal(sos.status, 200);
        await expect(card).toContainText("không gọi dịch vụ cứu hộ");
        const denied = await sessions.passenger2.page.request.get(
          base + `/api/bookings/${b.id}`,
        );
        assert.ok([403, 404].includes(denied.status()));
        return {
          page: p,
          observed:
            "Link công khai mở được; SOS ghi cảnh báo có nhãn mô phỏng; người khác không xem được booking",
          privacy_status: denied.status(),
        };
      },
      ["UAT-08"],
    );
    await test(
      "UAT-10",
      "Tài xế đến điểm đón, không phạt no-show sớm",
      async () => {
        const p = sessions.bike.page,
          b = state.bike,
          card = rideCard(p, b);
        const arrived = await action(
          p,
          `/rides/${b.ride_plan_id}/arrived`,
          () =>
            card
              .getByRole("button", { name: "Đã đến điểm đón", exact: true })
              .click(),
        );
        assert.equal(arrived.status, 200, JSON.stringify(arrived.body));
        await expect(
          card.getByRole("button", { name: /Khách không đến/ }),
        ).toBeDisabled();
        return {
          page: p,
          observed:
            "Ghi nhận đã đến; no-show trước hạn bị chặn, booking giữ CONFIRMED",
          guarded_in_ui: true,
        };
      },
      ["UAT-08"],
    );
    await test(
      "UAT-11",
      "Hoàn tất xe máy, đúng cước, thu nhập và đánh giá",
      async () => {
        const b = state.bike,
          p = sessions.passenger.page,
          price = await finish(sessions.bike.page, b);
        assert.equal(price.final_price_vnd, 81000);
        assert.equal(price.settlement.total_driver_payout_vnd, 64800);
        assert.equal(price.settlement.platform_net_amount_vnd, 16200);
        assert.equal(price.escrow.mode, "LOCAL_SIMULATION");
        await nav(p, "Hành trình của tôi");
        const card = bookingCard(p, b);
        await expect(
          card.getByRole("button", { name: "Gửi đánh giá", exact: true }),
        ).toBeVisible({ timeout: 15000 });
        await card.getByLabel("Điểm đánh giá").selectOption("4");
        await card
          .getByPlaceholder("Chia sẻ trải nghiệm của bạn")
          .fill("Nghiệm thu local: luồng xe máy hoàn tất.");
        const rating = await action(p, `/bookings/${b.id}/rating`, () =>
          card
            .getByRole("button", { name: "Gửi đánh giá", exact: true })
            .click(),
        );
        assert.equal(rating.status, 200);
        await card
          .getByRole("button", { name: "Giải thích giá", exact: true })
          .click();
        await expect(card.locator(".price-breakdown")).toContainText("64.800");
        await sessions.bike.context.close();
        return {
          page: p,
          observed:
            "Cước 81.000 = tài xế 64.800 + nền tảng 16.200; đánh giá gửi thành công",
          money: price.settlement,
        };
      },
      ["UAT-08"],
    );
    await test(
      "UAT-12",
      "Bao xe nội đô bốn người và hoàn tất",
      async () => {
        const p = sessions.passenger.page,
          m = await search(p, { seats: 4 });
        assert.ok(m.items.every((x) => x.service_code === "CAR_URBAN_PRIVATE"));
        const b = await select(p, "CAR_URBAN_PRIVATE");
        await accept(b);
        const price = await finish(driverFor(b), b);
        assert.equal(price.final_price_vnd, 194000);
        assert.equal(price.settlement.total_driver_payout_vnd, 155200);
        return {
          page: driverFor(b),
          observed:
            "Bốn người đi riêng, cước 194.000; tài xế 155.200 (hoa hồng nội đô 20%)",
          booking_id: b.id,
          money: price.settlement,
        };
      },
      ["UAT-11"],
    );
    await test(
      "UAT-13",
      "Pool hai ghế cùng booking vẫn là không ghép",
      async () => {
        const p = sessions.passenger.page;
        await search(p, { seats: 2 });
        const b = await select(p, "CAR_URBAN_POOL");
        await accept(b);
        const price = await finish(driverFor(b), b);
        assert.equal(price.final_price_vnd, 174000);
        assert.equal(price.settlement.guarantee_amount_vnd, 7300);
        assert.equal(price.settlement.total_driver_payout_vnd, 155200);
        return {
          page: driverFor(b),
          observed:
            "Hai ghế cùng booking không thành MATCHED; thu 174.000, Quỹ bù 7.300, tài xế nhận 155.200",
          booking_id: b.id,
          money: price.settlement,
        };
      },
      ["UAT-12"],
    );
    await test(
      "UAT-14",
      "Pool hai hành khách độc lập, khóa giá và đối soát",
      async () => {
        const p = sessions.passenger.page,
          p2 = sessions.passenger2.page;
        await search(p);
        const a = await select(p, "CAR_URBAN_POOL");
        await accept(a);
        await search(p2, { from: 2, to: 3 });
        const b = await select(p2, "CAR_URBAN_POOL");
        assert.equal(a.ride_plan_id, b.ride_plan_id);
        assert.equal(b.offer_id, null);
        await poll(
          p2,
          `/bookings/${b.id}`,
          (v) => v.escrow_status === "DEPOSITED",
        );
        const priceA = await finish(driverFor(a), a);
        const priceB = await poll(
          p2,
          `/bookings/${b.id}/price-breakdown`,
          (v) => v.escrow?.status === "RELEASED",
        );
        assert.equal(priceA.final_price_vnd, 143000);
        assert.equal(priceB.final_price_vnd, 105000);
        assert.equal(
          priceA.settlement.total_driver_payout_vnd +
            priceB.settlement.total_driver_payout_vnd,
          210800,
        );
        assert.equal(
          priceA.settlement.fund_contribution_vnd +
            priceB.settlement.fund_contribution_vnd,
          7440,
        );
        state.pool = [a, b];
        return {
          page: driverFor(a),
          observed:
            "A/B cùng xe; giá 143.000/105.000; tài xế 210.800; Quỹ +7.440",
          bookings: [a.id, b.id],
          money: [priceA.settlement, priceB.settlement],
        };
      },
      ["UAT-13"],
    );
    await test(
      "UAT-15",
      "Tài xế từ chối, chuyển offer; khách hủy sau ký quỹ",
      async () => {
        const second = await login("driver2");
        await online(second, true);
        const p = sessions.passenger.page;
        await search(p);
        const b = await select(p, "CAR_URBAN_PRIVATE");
        const assigned = driverFor(b),
          offer = assigned
            .locator(".offer-card")
            .filter({ hasText: b.id.slice(0, 8) });
        await offer.waitFor();
        const rejected = await action(
          assigned,
          `/offers/${b.offer_id}/reject`,
          () =>
            offer.getByRole("button", { name: "Từ chối", exact: true }).click(),
        );
        assert.equal(rejected.status, 200);
        const offered = await poll(
          p,
          `/bookings/${b.id}`,
          (v) => v.offer_id && v.offer_id !== b.offer_id,
        );
        assert.notEqual(offered.driver_id, b.driver_id);
        await accept(offered);
        const cancelled = await cancel(p, offered);
        assert.equal(cancelled.cancellation_fee_vnd, 0);
        const price = await poll(
          p,
          `/bookings/${b.id}/price-breakdown`,
          (v) => v.escrow?.status === "REFUNDED",
        );
        assert.equal(price.escrow.refunded_vnd, 194000);
        await online(second, false);
        await sessions.driver2.context.close();
        return {
          page: p,
          observed: "Offer sang tài xế khác; hủy trong ân hạn, hoàn đủ 194.000",
          booking_id: b.id,
        };
      },
      ["UAT-14"],
    );
    await test(
      "UAT-16",
      "Bao xe liên tỉnh đi ngay và thanh toán",
      async () => {
        const p = sessions.passenger.page,
          menu = await search(p, { to: 4 });
        assert.ok(
          menu.items.every((x) => x.service_code === "CAR_INTERCITY_PRIVATE"),
        );
        const b = await select(p, "CAR_INTERCITY_PRIVATE");
        await accept(b);
        const price = await finish(driverFor(b), b);
        assert.equal(price.final_price_vnd, 637000);
        assert.equal(price.settlement.total_driver_payout_vnd, 541450);
        return {
          page: driverFor(b),
          observed: "NOW chỉ có bao xe liên tỉnh; cước 637.000, tài xế 541.450",
          booking_id: b.id,
          money: price.settlement,
        };
      },
      ["UAT-15"],
    );
    await test(
      "UAT-17",
      "Tài xế đăng ghép liên tỉnh và hành khách đặt hai ghế",
      async () => {
        const now = new Date(
          (await data(sessions.admin.page, "/system")).server_time,
        ).getTime();
        state.trip = await publish(now + 4 * 86400000);
        const p = sessions.passenger2.page;
        await search(p, {
          to: 4,
          seats: 2,
          departure: state.trip.departure_time,
        });
        state.intercity = await select(p, "CAR_INTERCITY_POOL");
        assert.equal(state.intercity.scheduled_trip_id, state.trip.id);
        const b = await poll(
          p,
          `/bookings/${state.intercity.id}`,
          (v) => v.escrow_status === "DEPOSITED",
        );
        assert.equal(b.final_price_vnd, 400000);
        return {
          page: p,
          observed:
            "Đăng trước bốn ngày; giá tham chiếu 200.000/ghế; booking hai ghế ký quỹ 400.000",
          trip_id: state.trip.id,
          booking_id: b.id,
        };
      },
      ["UAT-16"],
    );
    await test(
      "UAT-18",
      "Thiếu ghế: hành khách đồng ý góp thêm tự nguyện",
      async () => {
        await advance(86400 + 5);
        const p = sessions.passenger2.page;
        await nav(p, "Hành trình của tôi");
        const card = bookingCard(p, state.intercity);
        const button = card.getByRole("button", {
          name: "Đồng ý góp thêm",
          exact: true,
        });
        await expect(button).toBeVisible({ timeout: 15000 });
        const offers = await data(p, "/intercity/topup-offers"),
          o = offers.find(
            (x) =>
              x.booking_id === state.intercity.id && x.status === "PENDING",
          );
        assert.equal(o.amount_vnd, 236000);
        const r = await action(
          p,
          `/intercity/topup-offers/${o.id}/respond`,
          () => button.click(),
        );
        assert.equal(r.status, 200);
        const b = await poll(
          p,
          `/bookings/${state.intercity.id}`,
          (v) => v.price_status === "TOPUP_LOCKED",
        );
        assert.equal(b.final_price_vnd, 636000);
        return {
          page: p,
          observed:
            "Khách chủ động ACCEPT +236.000; tổng booking 636.000, TOPUP_LOCKED",
          booking_id: b.id,
        };
      },
      ["UAT-17"],
    );
    await test(
      "UAT-19",
      "Liên tỉnh chốt thứ tự, chặn đi sớm, hoàn tất đúng tiền",
      async () => {
        if (process.env.UAT_RESUME_SOURCE) {
          const previous = JSON.parse(
            fs.readFileSync(process.env.UAT_RESUME_SOURCE, "utf8"),
          );
          const row = previous.results.find(
            (r) => r.id === "UAT-17" && r.status === "PASS",
          );
          assert.ok(row);
          state.intercity = await data(
            sessions.passenger2.page,
            `/bookings/${row.booking_id}`,
          );
          state.trip = (
            await data(sessions.driver.page, "/driver/pool-trips")
          ).find((t) => t.id === row.trip_id);
          assert.ok(state.trip);
        }
        const before = new Date(
          (await data(sessions.admin.page, "/system")).server_time,
        ).getTime();
        const fixAt =
          new Date(state.trip.departure_time).getTime() - 24 * 3600000 + 5000;
        if (before < fixAt) await advance(Math.ceil((fixAt - before) / 1000));
        const p = sessions.driver.page,
          b = state.intercity;
        await p.reload();
        await nav(p, "Dành cho tài xế");
        await p.locator(".driver-summary").waitFor();
        const card = rideCard(p, b);
        await card.waitFor();
        await expect(
          card.getByRole("button", { name: "Bắt đầu chuyến", exact: true }),
        ).toBeDisabled();
        const now = new Date(
          (await data(sessions.admin.page, "/system")).server_time,
        ).getTime();
        await advance(
          Math.ceil(
            (new Date(state.trip.departure_time).getTime() - now) / 1000,
          ) + 3,
        );
        const price = await finish(p, b);
        assert.equal(price.final_price_vnd, 636000);
        assert.equal(price.settlement.total_driver_payout_vnd, 540600);
        assert.equal(price.settlement.platform_net_amount_vnd, 95400);
        return {
          page: p,
          observed:
            "Chặn xuất phát sớm; sau giờ khởi hành hoàn tất, tài xế 540.600, nền tảng 95.400",
          money: price.settlement,
        };
      },
      ["UAT-18"],
    );
    await test(
      "UAT-20",
      "Từ chối góp thêm, tài xế hủy và hoàn tiền",
      async () => {
        const now = new Date(
            (await data(sessions.admin.page, "/system")).server_time,
          ).getTime(),
          trip = await publish(now + 4 * 86400000);
        const p = sessions.passenger.page;
        await search(p, { to: 4, departure: trip.departure_time });
        const b = await select(p, "CAR_INTERCITY_POOL");
        await poll(
          p,
          `/bookings/${b.id}`,
          (v) => v.escrow_status === "DEPOSITED",
        );
        await advance(86400 + 5);
        await nav(p, "Hành trình của tôi");
        const card = bookingCard(p, b),
          button = card.getByRole("button", { name: "Từ chối", exact: true });
        await expect(button).toBeVisible({ timeout: 15000 });
        const offers = await data(p, "/intercity/topup-offers"),
          o = offers.find(
            (x) => x.booking_id === b.id && x.status === "PENDING",
          );
        const declined = await action(
          p,
          `/intercity/topup-offers/${o.id}/respond`,
          () => button.click(),
        );
        assert.equal(declined.status, 200);
        const driver = sessions.driver.page,
          tripCard = driver
            .locator(".pool-trip-card")
            .filter({ hasText: trip.id.slice(0, 8) });
        await driver.reload();
        await nav(driver, "Dành cho tài xế");
        await driver.locator(".driver-summary").waitFor();
        const cancelButton = driver.getByRole("button", {
          name: "Hủy và hoàn tiền",
          exact: true,
        });
        await expect(cancelButton).toBeVisible({ timeout: 15000 });
        const cancelled = await action(
          driver,
          `/driver/pool-trips/${trip.id}/under-min-decision`,
          () => cancelButton.click(),
        );
        assert.equal(cancelled.status, 200);
        const price = await poll(
          p,
          `/bookings/${b.id}/price-breakdown`,
          (v) => v.escrow?.status === "REFUNDED",
        );
        assert.equal(price.escrow.refunded_vnd, 200000);
        return {
          page: p,
          observed:
            "Khách DECLINE; tài xế CANCEL; hoàn đủ 200.000, không thu phần góp thêm",
          booking_id: b.id,
        };
      },
      ["UAT-19"],
    );
    await test(
      "UAT-21",
      "Giao diện hành khách và tài xế ở ba kích thước",
      async () => {
        const checks = [];
        for (const slug of ["passenger", "driver"]) {
          const p = sessions[slug].page;
          await nav(
            p,
            slug === "driver" ? "Dành cho tài xế" : "Hành trình của tôi",
          );
          for (const width of [375, 768, 1440]) {
            await p.setViewportSize({ width, height: 900 });
            await p.waitForTimeout(250);
            const size = await p.evaluate(() => ({
              viewport: innerWidth,
              content: document.documentElement.scrollWidth,
            }));
            const overflow = size.content > size.viewport + 1;
            checks.push({ actor: slug, width, ...size, overflow });
            await screenshot(p, `UAT-21-${slug}-${width}`);
          }
        }
        fs.writeFileSync(
          path.join(out, "responsive.json"),
          JSON.stringify(checks, null, 2),
        );
        if (checks.some((x) => x.overflow))
          findings.push({
            id: "F-UI-01",
            severity: "MAJOR",
            title: "Giao diện tài xế tràn ngang trên màn hình nhỏ",
            case_id: "UAT-21",
            checks: checks.filter((x) => x.overflow),
          });
        assert.ok(
          checks.every((x) => !x.overflow),
          JSON.stringify(checks),
        );
        return { observed: "Không tràn ngang ở 375/768/1440 px", checks };
      },
      ["UAT-01"],
    );
    await test(
      "UAT-22",
      "Audit tự động khả năng truy cập",
      async () => {
        const source = fs.readFileSync(
            process.env.UAT_AXE_PATH ||
              path.join(out, "qa-tools/node_modules/axe-core/axe.min.js"),
            "utf8",
          ),
          audits = [];
        for (const slug of ["passenger", "passenger-plan", "driver"]) {
          const p =
            sessions[slug === "passenger-plan" ? "passenger" : slug].page;
          if (slug === "passenger") await nav(p, "Hành trình của tôi");
          if (slug === "passenger-plan") await nav(p, "Tìm chuyến");
          if (slug === "driver") await nav(p, "Dành cho tài xế");
          await p.setViewportSize({ width: 1440, height: 1000 });
          await p.addScriptTag({ content: source });
          const audit = await p.evaluate(async () => {
            const r = await window.axe.run(document, {
              runOnly: {
                type: "tag",
                values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"],
              },
            });
            return {
              violations: r.violations.map((v) => ({
                id: v.id,
                impact: v.impact,
                help: v.help,
                nodes: v.nodes.map((n) => ({
                  target: n.target,
                  failureSummary: n.failureSummary,
                })),
              })),
              passes: r.passes.length,
              incomplete: r.incomplete.map((v) => ({
                id: v.id,
                nodes: v.nodes.length,
              })),
            };
          });
          audits.push({ actor: slug, ...audit });
          if (audit.violations.length)
            findings.push({
              id: `F-A11Y-${slug}`,
              severity: "ACCESSIBILITY",
              title: `Axe phát hiện ${audit.violations.length} loại vi phạm ở ${slug}`,
              case_id: "UAT-22",
            });
        }
        fs.writeFileSync(
          path.join(out, "accessibility.json"),
          JSON.stringify(audits, null, 2),
        );
        assert.ok(
          audits.every((audit) => !audit.violations.length),
          "Axe còn vi phạm; xem accessibility.json",
        );
        return {
          observed:
            "Đã thực thi axe; các vi phạm ghi riêng, không coi audit tự động là chứng nhận WCAG",
          audits,
        };
      },
      ["UAT-01"],
    );
    await test(
      "UAT-23",
      "Đăng xuất và ngăn đọc lại dữ liệu riêng",
      async () => {
        const p = sessions.passenger.page;
        await p.setViewportSize({ width: 1440, height: 1000 });
        const button = p.getByRole("button", {
          name: "Đăng xuất",
          exact: true,
        });
        const r = await action(p, "/auth/logout", () => button.click());
        assert.equal(r.status, 200);
        await expect(
          p.getByRole("button", { name: "Đăng nhập", exact: true }),
        ).toBeVisible();
        const denied = await p.request.get(base + "/api/bookings");
        assert.equal(denied.status(), 401);
        return {
          page: p,
          observed:
            "Trở về đăng nhập; đọc bookings bằng phiên đã đăng xuất bị 401",
        };
      },
      ["UAT-01"],
    );
    await test(
      "UAT-24",
      "Điều hướng tài xế bằng bàn phím",
      async () => {
        const p = sessions.driver.page;
        await p.setViewportSize({ width: 1440, height: 1000 });
        await p
          .getByRole("navigation")
          .getByRole("button", { name: "Tìm chuyến", exact: true })
          .focus();
        await p.keyboard.press("Enter");
        await expect(p.locator(".trip-form")).toBeVisible();
        await p.keyboard.press("Tab");
        await expect(
          p
            .getByRole("navigation")
            .getByRole("button", { name: "Hành trình của tôi", exact: true }),
        ).toBeFocused();
        await p.keyboard.press("Enter");
        await expect(
          p.getByRole("heading", {
            name: "Từ xác nhận đến điểm đến",
            exact: true,
          }),
        ).toBeVisible();
        return {
          page: p,
          observed:
            "Tab/Enter chuyển được hai mục điều hướng; chưa kiểm thử trình đọc màn hình",
        };
      },
      ["UAT-01"],
    );
    await test(
      "UAT-25",
      "Thông tin quyết định nhận offer của tài xế",
      async () => {
        const p = sessions.passenger2.page,
          d = sessions.driver.page;
        await nav(d, "Dành cho tài xế");
        await search(p);
        const b = await select(p, "CAR_URBAN_PRIVATE");
        const offer = d
          .locator(".offer-card")
          .filter({ hasText: b.id.slice(0, 8) });
        await offer.waitFor();
        const text = await offer.innerText();
        const evidence = await screenshot(d, "UAT-25-offer");
        await cancel(p, b);
        const complete =
          text.includes("Phenikaa") &&
          text.includes("Đống Đa") &&
          text.includes("Thu nhập") &&
          text.includes("giờ");
        const countdown = Number((text.match(/(\d+) giây/) || [])[1]);
        assert.ok(
          countdown > 0 && countdown <= 60,
          `Đồng hồ offer sai: ${countdown}`,
        );
        if (!complete)
          findings.push({
            id: "F-DRIVER-01",
            severity: "MAJOR",
            title:
              "Offer thiếu điểm đón/trả và thu nhập dự kiến để quyết định nhận chuyến",
            case_id: "UAT-25",
            evidence,
            observed: text,
          });
        assert.ok(
          complete,
          "Offer thiếu điểm đón/trả hoặc thu nhập dự kiến; đã hủy booking thử, không nhận tiền",
        );
        return { page: d, observed: text };
      },
      ["UAT-01"],
    );
    await test(
      "UAT-26",
      "Khách không đến sau đủ thời gian: thu đúng phí, hoàn phần còn lại",
      async () => {
        if (sessions.bike.page.isClosed()) await login("bike");
        const p = sessions.passenger2.page,
          d = sessions.bike.page;
        await nav(d, "Dành cho tài xế");
        await online(d, true);
        await search(p);
        const b = await select(p, "BIKE_URBAN");
        await accept(b);
        const card = rideCard(d, b);
        const arrived = await action(
          d,
          `/rides/${b.ride_plan_id}/arrived`,
          () =>
            card
              .getByRole("button", { name: "Đã đến điểm đón", exact: true })
              .click(),
        );
        assert.equal(arrived.status, 200);
        const rides = await data(d, "/driver/rides");
        const eligible = rides
          .find((r) => r.id === b.ride_plan_id)
          .bookings.find((r) => r.id === b.id).no_show_eligible_at;
        assert.ok(eligible);
        const now =
          new Date(
            (await data(sessions.admin.page, "/system")).server_time,
          ).getTime() / 1000;
        await advance(Math.ceil(eligible - now) + 2);
        const button = card.getByRole("button", { name: /Khách không đến/ });
        await expect(button).toBeEnabled({ timeout: 15000 });
        const response = await action(d, `/bookings/${b.id}/no-show`, () =>
          button.click(),
        );
        assert.equal(response.status, 200);
        assert.equal(response.body.cancellation_fee_vnd, 16200);
        const detail = await poll(
          p,
          `/bookings/${b.id}/price-breakdown`,
          (v) => v.escrow?.status === "REFUNDED",
        );
        assert.equal(detail.escrow.refunded_vnd, 64800);
        return {
          page: d,
          booking_id: b.id,
          observed: "Chỉ mở nút sau hạn; phí 16.200, hoàn 64.800",
          money: detail.settlement,
        };
      },
      ["UAT-01"],
    );

    await test(
      "UAT-27",
      "Tài xế báo sự cố và hoàn toàn bộ ký quỹ",
      async () => {
        const p = sessions.passenger2.page,
          d = sessions.driver.page;
        await nav(d, "Dành cho tài xế");
        await search(p);
        const b = await select(p, "CAR_URBAN_PRIVATE");
        await accept(b);
        const card = rideCard(d, b);
        await card
          .getByRole("button", { name: "Báo sự cố", exact: true })
          .click();
        const response = await action(d, `/rides/${b.ride_plan_id}/abort`, () =>
          card
            .getByRole("button", { name: "Xác nhận dừng chuyến", exact: true })
            .click(),
        );
        assert.equal(response.status, 200);
        const detail = await poll(
          p,
          `/bookings/${b.id}/price-breakdown`,
          (v) => v.escrow?.status === "REFUNDED",
        );
        assert.equal(detail.escrow.refunded_vnd, 194000);
        assert.equal(
          (await data(p, `/bookings/${b.id}`)).ride_status,
          "CANCELLED_BY_DRIVER",
        );
        return {
          page: p,
          booking_id: b.id,
          observed: "Hủy do tài xế: hoàn 194.000, không thu phí khách",
        };
      },
      ["UAT-01"],
    );

    await test(
      "UAT-28",
      "Khách hủy bao xe nội đô sau ân hạn: đúng phí trần",
      async () => {
        const p = sessions.passenger2.page;
        await search(p);
        const b = await select(p, "CAR_URBAN_PRIVATE");
        await accept(b);
        await advance(121);
        const cancelled = await cancel(p, b);
        assert.equal(cancelled.cancellation_fee_vnd, 20000);
        const detail = await poll(
          p,
          `/bookings/${b.id}/price-breakdown`,
          (v) => v.escrow?.status === "REFUNDED",
        );
        assert.equal(detail.escrow.refunded_vnd, 174000);
        return {
          page: p,
          booking_id: b.id,
          observed: "Phí min(20.000, 20%): 20.000; hoàn 174.000",
          money: detail.settlement,
        };
      },
      ["UAT-01"],
    );

    await test(
      "UAT-29",
      "Tài xế từ chối ghép: khóa trần ghép, không hưởng bảo đảm Quỹ",
      async () => {
        const me = await sessions.passenger.page.request.get(
          base + "/api/auth/me",
        );
        if (me.status() !== 200) await login("passenger");
        const p = sessions.passenger.page,
          p2 = sessions.passenger2.page,
          d = sessions.driver.page;
        await nav(d, "Dành cho tài xế");
        await search(p);
        const a = await select(p, "CAR_URBAN_POOL");
        await accept(a);
        await search(p2, { from: 2, to: 3 });
        const b = await select(p2, "CAR_URBAN_POOL");
        assert.equal(a.ride_plan_id, b.ride_plan_id);
        await poll(
          p2,
          `/bookings/${b.id}`,
          (v) => v.escrow_status === "DEPOSITED",
        );
        const card = rideCard(d, a),
          member = card
            .locator(".ride-booking")
            .filter({ hasText: b.id.slice(0, 8) });
        const response = await action(
          d,
          `/rides/${a.ride_plan_id}/coriders/${b.id}/decline`,
          () => member.getByRole("button", { name: /Từ chối ghép/ }).click(),
        );
        assert.equal(response.status, 200);
        const refunded = await poll(
          p2,
          `/bookings/${b.id}/price-breakdown`,
          (v) => v.escrow?.status === "REFUNDED",
        );
        assert.equal(refunded.escrow.refunded_vnd, b.quoted_price_cap_vnd);
        const detail = await finish(d, a);
        assert.equal(detail.final_price_vnd, 155000);
        assert.equal(detail.settlement.total_driver_payout_vnd, 131750);
        assert.equal(detail.settlement.guarantee_amount_vnd, 0);
        return {
          page: d,
          bookings: [a.id, b.id],
          observed: "Khách gốc trả 155.000, tài xế 131.750; bảo đảm Quỹ bằng 0",
          money: detail.settlement,
        };
      },
      ["UAT-01"],
    );

    await test(
      "UAT-30",
      "Liên tỉnh đủ ba ghế tự nhiên: hoa hồng 10%, không góp thêm",
      async () => {
        const d = sessions.driver.page,
          p = sessions.passenger.page,
          p2 = sessions.passenger2.page;
        await nav(d, "Dành cho tài xế");
        const now = new Date(
          (await data(sessions.admin.page, "/system")).server_time,
        ).getTime();
        const trip = await publish(now + 4 * 86400000);
        await search(p, { to: 4, seats: 2, departure: trip.departure_time });
        const a = await select(p, "CAR_INTERCITY_POOL");
        await search(p2, { to: 4, departure: trip.departure_time });
        const b = await select(p2, "CAR_INTERCITY_POOL");
        await poll(
          p2,
          `/bookings/${b.id}`,
          (v) => v.escrow_status === "DEPOSITED",
        );
        await advance(86400 + 5);
        const confirmed = (await data(d, "/driver/pool-trips")).find(
          (r) => r.id === trip.id,
        );
        assert.equal(confirmed.status, "CONFIRMED");
        await advance(3 * 86400);
        const detail = await finish(d, a);
        const other = await poll(
          p2,
          `/bookings/${b.id}/price-breakdown`,
          (v) => v.escrow?.status === "RELEASED",
        );
        assert.equal(detail.final_price_vnd + other.final_price_vnd, 600000);
        assert.equal(
          detail.settlement.total_driver_payout_vnd +
            other.settlement.total_driver_payout_vnd,
          540000,
        );
        return {
          page: d,
          bookings: [a.id, b.id],
          observed: "3 ghế × 200.000, tài xế 540.000, nền tảng 60.000",
          money: [detail.settlement, other.settlement],
        };
      },
      ["UAT-29"],
    );

    await test(
      "UAT-31",
      "Thiếu khách, từ chối góp thêm và tài xế tự nguyện chạy dưới ngưỡng",
      async () => {
        const d = sessions.driver.page,
          p = sessions.passenger2.page;
        await nav(d, "Dành cho tài xế");
        const now = new Date(
          (await data(sessions.admin.page, "/system")).server_time,
        ).getTime();
        const trip = await publish(now + 4 * 86400000);
        await search(p, { to: 4, departure: trip.departure_time });
        const b = await select(p, "CAR_INTERCITY_POOL");
        await poll(
          p,
          `/bookings/${b.id}`,
          (v) => v.escrow_status === "DEPOSITED",
        );
        await advance(86400 + 5);
        await nav(p, "Hành trình của tôi");
        const card = bookingCard(p, b);
        const offers = await data(p, "/intercity/topup-offers"),
          offer = offers.find(
            (o) => o.booking_id === b.id && o.status === "PENDING",
          );
        assert.ok(offer);
        const declined = await action(
          p,
          `/intercity/topup-offers/${offer.id}/respond`,
          () =>
            card.getByRole("button", { name: "Từ chối", exact: true }).click(),
        );
        assert.equal(declined.status, 200);
        const run = await action(
          d,
          `/driver/pool-trips/${trip.id}/under-min-decision`,
          () =>
            d
              .getByRole("button", { name: "Chạy dưới ngưỡng", exact: true })
              .click(),
        );
        assert.equal(run.status, 200);
        assert.equal(run.body.status, "CONFIRMED_UNDER_MIN");
        await advance(3 * 86400);
        const detail = await finish(d, b);
        assert.equal(detail.final_price_vnd, 200000);
        assert.equal(detail.settlement.total_driver_payout_vnd, 180000);
        return {
          page: d,
          booking_id: b.id,
          observed:
            "Khách giữ giá 200.000, không bị ép góp thêm; tài xế 180.000",
          money: detail.settlement,
        };
      },
      ["UAT-30"],
    );
  } finally {
    save();
    await browser.close();
    const summary = {
      passed: results.filter((x) => x.status === "PASS").length,
      failed: results.filter((x) => x.status === "FAIL").length,
      blocked: results.filter((x) => x.status === "BLOCKED").length,
      findings: findings.length,
      runtime_errors: runtimeErrors.length,
      http_5xx: network.filter((r) => r.status >= 500).length,
      http_429: network.filter((r) => r.status === 429).length,
    };
    fs.writeFileSync(
      path.join(out, "summary.json"),
      JSON.stringify(summary, null, 2),
    );
    console.log(JSON.stringify(summary));
    if (
      summary.failed ||
      summary.blocked ||
      summary.runtime_errors ||
      summary.http_5xx
    )
      process.exitCode = 1;
  }
})().catch((error) => {
  console.error(redact(error.message));
  process.exitCode = 1;
});
