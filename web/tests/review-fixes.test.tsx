import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { serverNow, syncServerTime } from "@/lib/server-clock";
import { ApiError } from "@/lib/api";
import { ErrorNotice } from "@/components/ui";
import { TripForm, places } from "@/components/trip-form";

afterEach(() => {
  vi.useRealTimers();
  syncServerTime(String(Date.now()));
});

describe("acceptance regressions", () => {
  it("uses server time after a five-day demo advance", () => {
    const advanced = Date.now() + 5 * 86400000;
    syncServerTime(String(advanced));
    expect(Math.abs(serverNow() - advanced)).toBeLessThan(100);
    expect(Math.ceil((advanced + 20000 - serverNow()) / 1000)).toBe(20);
  });

  it("disables retry until Retry-After elapses", () => {
    vi.useFakeTimers();
    const retry = vi.fn();
    render(
      <ErrorNotice
        error={new ApiError(429, "RATE_LIMITED", "Vui lòng chờ", 2000)}
        retry={retry}
      />,
    );
    const button = screen.getByRole("button", { name: /Thử lại/ });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(retry).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(button).toBeEnabled();
  });

  it("discards a late search response when the passenger edits the intent", async () => {
    let resolve!: (response: Response) => void;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    );
    const created = vi.fn(),
      changed = vi.fn();
    render(
      <TripForm
        pickup={places[0]}
        dropoff={places[1]}
        onPickup={() => undefined}
        onDropoff={() => undefined}
        mapTarget="pickup"
        onMapTarget={() => undefined}
        onCreated={created}
        onIntentChange={changed}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Tìm chuyến phù hợp/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("Tối đa có thể trả"), {
      target: { value: "900000" },
    });
    expect(changed).toHaveBeenCalled();
    await act(async () => {
      resolve(new Response(JSON.stringify({ id: "old-search" })));
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Tìm chuyến phù hợp/ }),
      ).toBeEnabled(),
    );
    expect(created).not.toHaveBeenCalled();
  });
});
