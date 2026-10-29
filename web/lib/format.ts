import type { ServiceCode } from "./types";

export const serviceNames: Record<ServiceCode, string> = {
  BIKE_URBAN: "Xe máy nội đô",
  CAR_URBAN_PRIVATE: "Taxi bao xe",
  CAR_URBAN_POOL: "Taxi ghép nội đô",
  CAR_INTERCITY_PRIVATE: "Bao xe liên tỉnh",
  CAR_INTERCITY_POOL: "Ghép xe liên tỉnh",
};

export function money(value: unknown): string {
  const numeric =
    typeof value === "number"
      ? value
      : typeof value === "string"
        ? Number(value)
        : NaN;
  return Number.isFinite(numeric)
    ? `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(numeric)} đ`
    : "—";
}

export function dateTime(value: unknown): string {
  const date =
    typeof value === "number"
      ? new Date(value * 1000)
      : typeof value === "string"
        ? new Date(value)
        : null;
  if (!date || !Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function humanStatus(value: string | undefined): string {
  if (!value) return "Chưa có";
  const names: Record<string, string> = {
    HELD: "Đang chờ tài xế",
    CONFIRMED: "Đã xác nhận",
    RIDE_STARTED: "Đang di chuyển",
    COMPLETED: "Đã hoàn thành",
    EXPIRED: "Đã hết thời gian",
    CANCELLED_BY_PASSENGER: "Khách đã hủy",
    CANCELLED_BY_DRIVER: "Tài xế đã hủy",
    CANCELLED_BY_SYSTEM: "Hệ thống đã hủy",
    NO_SHOW: "Khách không đến",
    QUOTED: "Đã báo giá",
    FIXED_LOCKED: "Giá cố định",
    POOL_SEARCHING: "Đang tìm người ghép",
    MATCHED_LOCKED: "Đã ghép · Khóa giá",
    UNMATCHED_LOCKED: "Không ghép · Khóa giá",
    MERGED_REDUCED_LOCKED: "Đã giảm giá sau gộp",
    TOPUP_LOCKED: "Đã góp thêm",
    NONE: "Chưa ký quỹ",
    DEPOSIT_PENDING: "Đang chờ ký quỹ",
    DEPOSITED: "Đã ký quỹ",
    LOCKED: "Đã khóa giá ký quỹ",
    TOPPED_UP: "Đã nạp thêm",
    RELEASED: "Đã giải ngân",
    REFUNDED: "Đã hoàn tiền",
    ESCROW_FAILED: "Ký quỹ thất bại",
    DISPUTED: "Đang tranh chấp",
    RESOLVED: "Đã phân xử",
    PENDING: "Đang chờ",
    VERIFIED: "Đã xác minh",
    REJECTED: "Đã từ chối",
    OPEN_FOR_BOOKING: "Đang nhận khách",
    BOOKING_CLOSED: "Đã đóng đặt chỗ",
    UNDER_MIN_DRIVER_DECISION: "Chờ quyết định chạy",
    CONFIRMED_UNDER_MIN: "Chạy dưới ngưỡng",
    CONFIRMED_TOPUP: "Chạy với góp thêm",
    TOPUP_OFFERED: "Đang đề nghị góp thêm",
    CANCELLED_LOW_DEMAND: "Hủy do thiếu khách",
    PICKUP_ORDER_FIXED: "Đã chốt thứ tự đón",
    DEPARTED: "Đã xuất phát",
    MERGED: "Đã gộp chuyến",
    MERGE_PENDING_CONFIRMATION: "Chờ xác nhận gộp",
    PLAN_OPEN_SEARCHING: "Đang mở ghép",
    PLAN_CLOSED_TO_NEW: "Đã đóng ghép",
    PLAN_COMPLETED: "Hoàn tất kế hoạch",
    PLAN_ABORTED: "Dừng do sự cố",
  };
  return names[value] ?? value.replaceAll("_", " ");
}

export function localDateInput(date: Date): string {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function numberField(
  record: Record<string, unknown>,
  ...keys: string[]
): number | undefined {
  for (const key of keys) {
    const v = record[key];
    if (
      (typeof v === "number" || typeof v === "string") &&
      Number.isFinite(Number(v))
    )
      return Number(v);
  }
  return undefined;
}
