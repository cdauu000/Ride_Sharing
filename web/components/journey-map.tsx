"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Point, RoadRoute } from "@/lib/types";
import { RouteMap } from "./route-map";
import { ErrorNotice } from "./ui";

export function JourneyMap({
  pickup,
  dropoff,
  pending,
  target,
  onPick,
  pricingFixture = false,
}: {
  pickup: Point;
  dropoff: Point;
  pending: boolean;
  target: "pickup" | "dropoff";
  onPick: (point: Point, target?: "pickup" | "dropoff") => void;
  pricingFixture?: boolean;
}) {
  const [result, setResult] = useState<{
    key: string;
    route?: RoadRoute;
    error?: unknown;
  }>();
  const [retry, setRetry] = useState(0);
  const key = JSON.stringify([
    pickup.lat,
    pickup.lon,
    dropoff.lat,
    dropoff.lon,
  ]);
  const valid =
    [pickup.lat, pickup.lon, dropoff.lat, dropoff.lon].every(Number.isFinite) &&
    Math.abs(pickup.lat) <= 90 &&
    Math.abs(dropoff.lat) <= 90 &&
    Math.abs(pickup.lon) <= 180 &&
    Math.abs(dropoff.lon) <= 180;
  const same = pickup.lat === dropoff.lat && pickup.lon === dropoff.lon;
  useEffect(() => {
    if (pending || !valid || same) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    const load = async () => {
      try {
        const route = await api<RoadRoute>("/locations/route", {
          method: "POST",
          signal: controller.signal,
          body: JSON.stringify({
            pickup: { lat: pickup.lat, lon: pickup.lon },
            dropoff: { lat: dropoff.lat, lon: dropoff.lon },
          }),
        });
        if (
          !Number.isFinite(route.distance_m) ||
          !route.geometry?.coordinates?.length
        )
          throw new Error("Chưa nhận được lộ trình hợp lệ. Vui lòng thử lại.");
        if (!controller.signal.aborted) setResult({ key, route });
      } catch (error) {
        if (controller.signal.aborted) return;
        if (
          error instanceof ApiError &&
          error.code === "ROUTE_PREVIEW_BUSY" &&
          ++attempts < 4
        ) {
          timer = setTimeout(
            () => void load(),
            Math.max(1200, error.retryAfterMs),
          );
        } else setResult({ key, error });
      }
    };
    setResult(undefined);
    timer = setTimeout(() => void load(), 650);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [
    key,
    pickup.lat,
    pickup.lon,
    dropoff.lat,
    dropoff.lon,
    pending,
    valid,
    same,
    retry,
  ]);
  const current =
    !pending && valid && !same && result?.key === key ? result : undefined;
  const route = current?.route;
  return (
    <>
      <RouteMap
        pickup={pickup}
        dropoff={dropoff}
        target={target}
        onPick={onPick}
        route={route}
      />
      <div
        className="route-summary"
        aria-live="polite"
        aria-label="Tổng quãng đường"
      >
        {pending ? (
          <p>Chọn địa chỉ trong kết quả tìm kiếm để tính lại quãng đường.</p>
        ) : !valid ? (
          <p>Vui lòng nhập tọa độ hợp lệ.</p>
        ) : same ? (
          <p>Điểm đón và điểm đến đang trùng nhau: 0 km.</p>
        ) : route ? (
          <>
            <strong>
              {(route.distance_m / 1000).toLocaleString("vi-VN", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}{" "}
              km
            </strong>
            <span>
              Đường bộ bằng ô tô · khoảng {Math.ceil(route.duration_s / 60)}{" "}
              phút
            </span>
            <small>
              Ước tính theo mạng đường, chưa tính giao thông trực tiếp. Xe máy
              có thể đi tuyến khác.
            </small>
            {pricingFixture && (
              <small>
                Bản thử nghiệm: giá chuyến sử dụng dữ liệu kiểm thử riêng.
              </small>
            )}
            {route.waypoints.some((p) => p.distance_m > 50) && (
              <p className="route-snap-warning">
                Ghim cách đường ô tô: điểm đón{" "}
                {Math.round(route.waypoints[0].distance_m)} m, điểm đến{" "}
                {Math.round(route.waypoints[1].distance_m)} m. Kiểm tra cổng đón
                và đoạn di chuyển đến đường.
              </p>
            )}
            <small>
              Lộ trình:{" "}
              <a
                href="https://www.openstreetmap.org/copyright"
                target="_blank"
                rel="noreferrer"
              >
                © OpenStreetMap
              </a>{" "}
              ·{" "}
              <a
                href="https://routing.openstreetmap.de/about.html"
                target="_blank"
                rel="noreferrer"
              >
                OSRM / FOSSGIS
              </a>{" "}
              ·{" "}
              <a
                href="https://www.openstreetmap.org/fixthemap"
                target="_blank"
                rel="noreferrer"
              >
                Báo lỗi bản đồ
              </a>
            </small>
          </>
        ) : current?.error ? (
          <>
            <ErrorNotice error={current.error} />
            <button
              type="button"
              className="text-button"
              onClick={() => setRetry((v) => v + 1)}
            >
              Tính lại quãng đường
            </button>
          </>
        ) : (
          <p>Đang tính quãng đường bộ…</p>
        )}
      </div>
    </>
  );
}
