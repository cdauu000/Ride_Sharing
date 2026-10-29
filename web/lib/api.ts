import type { JsonObject } from "./types";
import { userErrorMessage, validationMessage } from "./errors";
import { syncServerTime } from "./server-clock";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryAfterMs = 0,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let refreshPending: Promise<boolean> | null = null;
let readRetryAt = 0;

async function refreshSession(): Promise<boolean> {
  if (!refreshPending) {
    refreshPending = fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: "{}",
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshPending = null;
      });
  }
  return refreshPending;
}

function errorMessage(
  payload: unknown,
  status: number,
): { code: string; message: string } {
  if (typeof payload !== "object" || payload === null)
    return {
      code: "NETWORK_RESPONSE",
      message: `Không thể xử lý yêu cầu (${status}).`,
    };
  const data = payload as JsonObject;
  const detail = data.detail ?? data.error ?? data;
  if (typeof detail === "string") return { code: detail, message: detail };
  if (Array.isArray(detail))
    return {
      code: "VALIDATION_ERROR",
      message: validationMessage(detail),
    };
  if (typeof detail === "object" && detail !== null) {
    const obj = detail as JsonObject;
    return {
      code: String(obj.code ?? data.code ?? "REQUEST_FAILED"),
      message: String(
        obj.message ??
          obj.code ??
          data.message ??
          `Yêu cầu thất bại (${status}).`,
      ),
    };
  }
  return {
    code: String(data.code ?? "REQUEST_FAILED"),
    message: String(data.message ?? `Yêu cầu thất bại (${status}).`),
  };
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  if (
    (!options.method || options.method === "GET") &&
    !path.startsWith("/auth/") &&
    Date.now() < readRetryAt
  ) {
    throw new ApiError(
      429,
      "RATE_LIMITED",
      userErrorMessage("RATE_LIMITED"),
      readRetryAt - Date.now(),
    );
  }
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      credentials: path.startsWith("/surveys/") ? "omit" : "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch {
    throw new ApiError(
      0,
      "CONNECTION_FAILED",
      "Chưa kết nối được máy chủ. Hãy kiểm tra backend và thử lại.",
    );
  }
  if (
    response.status === 401 &&
    !path.startsWith("/surveys/") &&
    ![
      "/auth/login",
      "/auth/register",
      "/auth/refresh",
      "/auth/logout",
    ].includes(path) &&
    (await refreshSession())
  ) {
    try {
      response = await fetch(`/api${path}`, {
        ...options,
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json", ...options.headers },
      });
    } catch {
      throw new ApiError(
        0,
        "CONNECTION_FAILED",
        "Chưa kết nối được máy chủ. Hãy kiểm tra backend và thử lại.",
      );
    }
  }
  const payload: unknown =
    response.status === 204 ? null : await response.json().catch(() => null);
  syncServerTime(response.headers.get("X-Server-Time"));
  if (path === "/system" && typeof payload === "object" && payload !== null) {
    const value = (payload as JsonObject).server_time;
    if (typeof value === "string") syncServerTime(value);
  }
  if (!response.ok) {
    const error = errorMessage(payload, response.status);
    const retryHeader = response.headers.get("Retry-After");
    const seconds = retryHeader ? Number(retryHeader) : 0;
    const retryAfterMs = Number.isFinite(seconds)
      ? Math.max(0, seconds * 1000)
      : Math.max(0, Date.parse(retryHeader ?? "") - Date.now()) || 0;
    if (
      response.status === 429 &&
      (!options.method || options.method === "GET")
    )
      readRetryAt = Date.now() + (retryAfterMs || 1000);
    throw new ApiError(
      response.status,
      error.code,
      userErrorMessage(error.code, error.message),
      retryAfterMs,
    );
  }
  if (
    path === "/auth/login" ||
    path === "/auth/register" ||
    path === "/auth/logout"
  )
    readRetryAt = 0;
  return payload as T;
}

const retryKeys = new Map<string, string>();

export async function mutate<T>(
  path: string,
  body: unknown = {},
  method = "POST",
  key?: string,
): Promise<T> {
  const serialized = JSON.stringify(body);
  const fingerprint = `${method}:${path}:${serialized}`;
  const idempotencyKey =
    key ?? retryKeys.get(fingerprint) ?? crypto.randomUUID();
  retryKeys.set(fingerprint, idempotencyKey);
  try {
    const response = await api<T>(path, {
      method,
      body: serialized,
      headers: { "Idempotency-Key": idempotencyKey },
    });
    retryKeys.delete(fingerprint);
    return response;
  } catch (error) {
    // The server may have committed before transport or server failure reached us.
    if (
      !(error instanceof ApiError) ||
      (error.status !== 0 && error.status < 500)
    )
      retryKeys.delete(fingerprint);
    throw error;
  }
}

export const fetcher = <T>(path: string): Promise<T> => api<T>(path);
