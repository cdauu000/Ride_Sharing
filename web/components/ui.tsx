"use client";

import {
  ArrowRight,
  LoaderCircle,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";

export function ErrorNotice({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  const [retryAt, setRetryAt] = useState(0);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const delay = error instanceof ApiError ? error.retryAfterMs : 0;
    setRetryAt(delay ? Date.now() + delay : 0);
    setNow(Date.now());
  }, [error]);
  useEffect(() => {
    if (!retryAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [retryAt]);
  if (!error) return null;
  const wait = Math.max(0, Math.ceil((retryAt - now) / 1000));
  const message =
    error instanceof Error ? error.message : "Có lỗi xảy ra khi xử lý yêu cầu.";
  return (
    <div className="notice error" role="alert">
      <TriangleAlert size={18} />
      <div>
        <strong>
          {error instanceof ApiError && error.code === "INVALID_CREDENTIALS"
            ? "Không đăng nhập được"
            : error instanceof ApiError && error.status === 401
              ? "Phiên đăng nhập đã hết hạn"
              : "Chưa thực hiện được"}
        </strong>
        <p>{message}</p>
        {wait > 0 && <p>Thử lại sau {wait} giây.</p>}
      </div>
      {retry && (
        <button
          type="button"
          className="icon-button"
          aria-label="Thử lại"
          onClick={retry}
          disabled={wait > 0}
        >
          <RefreshCw size={16} />
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-icon">{icon}</div>}
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

export function Loading({ label = "Đang tải dữ liệu…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={19} className="spin" />
      {label}
    </div>
  );
}

export function SectionTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note?: string;
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

export function SubmitButton({
  pending,
  children,
}: {
  pending: boolean;
  children: ReactNode;
}) {
  return (
    <button type="submit" className="primary" disabled={pending}>
      {pending ? <LoaderCircle className="spin" size={17} /> : null}
      {children}
      {!pending && <ArrowRight size={17} />}
    </button>
  );
}
