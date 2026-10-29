import { describe, expect, it, vi } from "vitest";
import { api, ApiError, mutate } from "@/lib/api";

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("API financial mutation boundary", () => {
  it("sends same-origin cookies and a supplied idempotency key", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(response({ id: "booking-1" }));
    const payload = await mutate<{ id: string }>(
      "/recommendations/run/select",
      { candidate_id: "candidate-1" },
      "POST",
      "fixed-test-key",
    );
    expect(payload.id).toBe("booking-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/recommendations/run/select",
      expect.objectContaining({
        credentials: "same-origin",
        method: "POST",
        headers: expect.objectContaining({
          "Idempotency-Key": "fixed-test-key",
        }),
      }),
    );
  });

  it("preserves the mutation key after an ambiguous transport failure", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new TypeError("connection dropped"))
      .mockResolvedValueOnce(response({ id: "single-booking" }));
    await expect(
      mutate("/test/retry-booking", { candidate_id: "same-candidate" }),
    ).rejects.toMatchObject({ code: "CONNECTION_FAILED" });
    await mutate("/test/retry-booking", { candidate_id: "same-candidate" });
    const firstOptions = fetchMock.mock.calls[0][1] as RequestInit;
    const secondOptions = fetchMock.mock.calls[1][1] as RequestInit;
    expect(
      (firstOptions.headers as Record<string, string>)["Idempotency-Key"],
    ).toBe(
      (secondOptions.headers as Record<string, string>)["Idempotency-Key"],
    );
  });

  it("refreshes an expired access session once and retains the original request", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response({ detail: "expired" }, 401))
      .mockResolvedValueOnce(response({ refreshed: true }))
      .mockResolvedValueOnce(response({ id: "me", role: "PASSENGER" }));
    const user = await api<{ id: string }>("/auth/me");
    expect(user.id).toBe("me");
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/auth/me",
      "/api/auth/refresh",
      "/api/auth/me",
    ]);
  });

  it("surfaces schema errors and never treats a rejected mutation as success", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response(
        { detail: [{ loc: ["body", "budget_max"], msg: "must be positive" }] },
        422,
      ),
    );
    await expect(
      mutate("/trip-requests", { budget_max: -1 }),
    ).rejects.toMatchObject({
      status: 422,
      code: "VALIDATION_ERROR",
      message: "Ngân sách tối đa: vui lòng kiểm tra giá trị hợp lệ.",
    });
  });

  it("does not silently retry incorrect login credentials", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response(
        {
          detail: {
            code: "INVALID_CREDENTIALS",
            message: "Sai thông tin đăng nhập",
          },
        },
        401,
      ),
    );
    await expect(
      mutate("/auth/login", { email: "test@example.com", password: "wrong" }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the payment key on server failure to prevent a duplicate retry", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response({ detail: "SERVER_ERROR" }, 502))
      .mockResolvedValueOnce(response({ id: "one-payment" }));
    await expect(mutate("/test/payment-502")).rejects.toMatchObject({
      status: 502,
    });
    await mutate("/test/payment-502");
    const keys = fetchMock.mock.calls.map(
      ([, options]) =>
        (options?.headers as Record<string, string>)["Idempotency-Key"],
    );
    expect(keys[0]).toBe(keys[1]);
  });

  it("respects Retry-After for polling without blocking logout", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: { code: "RATE_LIMITED" } }), {
          status: 429,
          headers: { "Retry-After": "12" },
        }),
      )
      .mockResolvedValueOnce(response({ logged_out: true }));
    await expect(api("/driver/rides")).rejects.toMatchObject({
      retryAfterMs: 12000,
    });
    await expect(api("/driver/offers")).rejects.toMatchObject({ status: 429 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await mutate("/auth/logout");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
