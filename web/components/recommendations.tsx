"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  ArrowRight,
  Bike,
  CarFront,
  Check,
  Clock3,
  Leaf,
  Route,
  Sparkles,
  UsersRound,
} from "lucide-react";
import { fetcher, mutate } from "@/lib/api";
import { money, numberField, serviceNames } from "@/lib/format";
import { useServerNow } from "@/lib/server-clock";
import type {
  Booking,
  Candidate,
  RecommendationRun,
  TripRequest,
} from "@/lib/types";
import { EmptyState, ErrorNotice, Loading, SectionTitle } from "./ui";

export function Recommendations({
  trip,
  onBooked,
}: {
  trip: TripRequest | null;
  onBooked: (booking: Booking) => void;
}) {
  const {
    data,
    error,
    isLoading,
    isValidating,
    mutate: refresh,
  } = useSWR<RecommendationRun>(
    trip ? `/trip-requests/${trip.id}/recommendations` : null,
    fetcher,
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const [pending, setPending] = useState<string | null>(null);
  const [selectError, setSelectError] = useState<unknown>();
  const now = useServerNow();
  const candidates =
    !trip || error || isValidating
      ? []
      : (data?.items ?? data?.candidates ?? []);
  async function select(candidate: Candidate) {
    if (!data || !trip || error || isValidating || pending) return;
    if (
      typeof candidate.expires_at === "string" &&
      Date.parse(candidate.expires_at) <= now
    )
      return;
    setPending(candidate.id);
    setSelectError(undefined);
    try {
      onBooked(
        await mutate<Booking>(
          `/recommendations/${data.run_id ?? data.id}/select`,
          { candidate_id: candidate.id },
        ),
      );
    } catch (caught) {
      setSelectError(caught);
    } finally {
      setPending(null);
    }
  }
  return (
    <section className="recommendations-section">
      <SectionTitle
        eyebrow="LỰA CHỌN CHO BẠN"
        title={trip ? "Tìm cách đi phù hợp" : "Một hành trình, nhiều cách đi"}
        description={
          trip
            ? `${trip.mode === "URBAN" ? "Nội đô" : "Liên tỉnh"} · ${trip.allowed_service_codes.length} dịch vụ đáp ứng nhu cầu`
            : "So sánh xe máy, taxi bao xe và đi ghép trong cùng một lần tìm kiếm."
        }
        action={
          trip ? (
            <button className="text-button" onClick={() => void refresh()}>
              Tìm lại <ArrowRight size={14} />
            </button>
          ) : undefined
        }
      />
      <ErrorNotice error={error} retry={() => void refresh()} />
      <ErrorNotice error={selectError} />
      {candidates.length > 0 &&
        candidates.every(
          (candidate) =>
            typeof candidate.expires_at === "string" &&
            Date.parse(candidate.expires_at) <= now,
        ) && (
          <p className="notice" role="status">
            Các phương án đã hết hạn. Chọn “Tìm lại” để cập nhật giá và chỗ
            trống.
          </p>
        )}
      {isLoading && (
        <Loading label="Đang kiểm tra lộ trình, chỗ trống và mức giá…" />
      )}
      {!trip && (
        <div className="service-intro">
          <div>
            <span className="service-icon bike">
              <Bike size={24} />
            </span>
            <h3>Gọn nhẹ mỗi ngày</h3>
            <p>Xe máy cho hành trình một người, không hành lý lớn.</p>
            <small>XE MÁY NỘI ĐÔ</small>
          </div>
          <div>
            <span className="service-icon pool">
              <UsersRound size={24} />
            </span>
            <h3>Cùng đi, cùng tiết kiệm</h3>
            <p>Ghép chuyến cùng hướng với giá trần rõ ràng.</p>
            <small>TAXI GHÉP</small>
          </div>
          <div>
            <span className="service-icon private">
              <CarFront size={24} />
            </span>
            <h3>Chủ động hành trình</h3>
            <p>Bao xe riêng tư cho nhóm đến bốn hành khách.</p>
            <small>NỘI ĐÔ & LIÊN TỈNH</small>
          </div>
        </div>
      )}
      {trip && !isLoading && !error && candidates.length === 0 && (
        <EmptyState icon={<Route size={26} />} title="Chưa có xe phù hợp">
          Thử mở rộng khung giờ, đổi điểm đón hoặc tìm lại sau. Các dịch vụ chỉ
          hiển thị khi có phương án đáp ứng ràng buộc hành trình.
        </EmptyState>
      )}
      <div className="recommendation-grid">
        {candidates.map((candidate, index) => (
          <CandidateCard
            key={candidate.id}
            candidate={candidate}
            recommended={index === 0}
            pending={pending === candidate.id}
            disabled={
              pending !== null ||
              (typeof candidate.expires_at === "string" &&
                Date.parse(candidate.expires_at) <= now)
            }
            onSelect={() => void select(candidate)}
          />
        ))}
      </div>
      {trip?.rejection_reasons &&
        Object.keys(trip.rejection_reasons).length > 0 && (
          <details className="rejection-details">
            <summary>Vì sao một số dịch vụ không khả dụng?</summary>
            <ul>
              {Object.entries(trip.rejection_reasons).map(
                ([service, reasons]) => (
                  <li key={service}>
                    <strong>
                      {serviceNames[service as keyof typeof serviceNames] ??
                        service}
                    </strong>
                    : {Array.isArray(reasons) ? reasons.join(" · ") : reasons}
                  </li>
                ),
              )}
            </ul>
          </details>
        )}
    </section>
  );
}

export function CandidateCard({
  candidate,
  recommended,
  pending,
  disabled,
  onSelect,
}: {
  candidate: Candidate;
  recommended: boolean;
  pending: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  const pool = candidate.service_code === "CAR_URBAN_POOL";
  const isBike = candidate.service_code === "BIKE_URBAN";
  const isPool = candidate.service_code.includes("POOL");
  const price = numberField(
    candidate,
    "price",
    "fare_vnd",
    "estimated_price",
    "expected_price_vnd",
  );
  const matched = numberField(
    candidate,
    "matched_estimate",
    "fare_matched_est_vnd",
  );
  const quote = numberField(candidate, "quote", "pool_quote_price_vnd");
  const cap =
    numberField(
      candidate,
      "unmatched",
      "pool_unmatched_price_vnd",
      "quoted_price_cap_vnd",
    ) ?? price;
  const duration = numberField(
    candidate,
    "duration_min",
    "in_vehicle_duration_min",
  );
  const eta = numberField(
    candidate,
    "pickup_eta_min",
    "planned_pickup_eta_min",
  );
  const matchLabel =
    typeof candidate.p_match_label === "string"
      ? candidate.p_match_label
      : candidate.p_match_est == null
        ? "Chưa đánh giá"
        : candidate.p_match_est >= 0.65
          ? "Cao"
          : candidate.p_match_est >= 0.35
            ? "Trung bình"
            : "Thấp";
  const driver =
    typeof candidate.driver_name === "string"
      ? candidate.driver_name
      : "Tài xế phù hợp";
  return (
    <article className={`candidate-card ${recommended ? "recommended" : ""}`}>
      <div className="candidate-header">
        <span
          className={`service-icon ${isBike ? "bike" : isPool ? "pool" : "private"}`}
        >
          {isBike ? (
            <Bike size={24} />
          ) : isPool ? (
            <UsersRound size={24} />
          ) : (
            <CarFront size={24} />
          )}
        </span>
        <div>
          <h3>{serviceNames[candidate.service_code]}</h3>
          <span>{driver}</span>
        </div>
        {recommended && (
          <span className="badge recommendation">
            <Sparkles size={11} />
            Đề xuất
          </span>
        )}
      </div>
      <div className="candidate-price">
        <strong>{money(pool ? matched : price)}</strong>
        <span>
          {pool
            ? "Dự kiến khi ghép được"
            : candidate.service_code === "CAR_INTERCITY_POOL"
              ? "Giá cho booking của bạn"
              : "Giá trọn chuyến"}
        </span>
      </div>
      <div className="candidate-times">
        <span>
          <Clock3 size={14} />
          {eta == null ? "—" : `${Math.ceil(eta)} phút`} đón
        </span>
        <span>
          <Route size={14} />
          {duration == null ? "—" : `${Math.ceil(duration)} phút`} đi
        </span>
      </div>
      {pool ? (
        <div className="pool-prices">
          <div>
            <span>Tối đa khi ghép được</span>
            <strong>{money(quote)}</strong>
          </div>
          <div>
            <span>Tối đa nếu không ghép</span>
            <strong>{money(cap)}</strong>
          </div>
          <div className="match-estimate">
            <span className="live-dot" />
            Khả năng ghép: <strong>{matchLabel}</strong>
          </div>
        </div>
      ) : (
        <p className="candidate-note">
          <Check size={14} />
          {isPool
            ? "Giá cố định lúc đặt · Góp thêm chỉ khi đồng ý"
            : "Đi riêng · Không ghép thêm hành khách"}
        </p>
      )}
      {pool && (
        <p className="candidate-note">
          <Leaf size={14} />
          Giá cuối cùng được khóa trong hành trình.
        </p>
      )}
      <div className="candidate-labels">
        {candidate.labels
          ?.filter((label) => label !== "Đề xuất")
          .map((label) => (
            <span key={label}>{label}</span>
          ))}
      </div>
      <button
        className={recommended ? "primary" : "secondary"}
        disabled={disabled}
        onClick={onSelect}
      >
        {pending ? "Đang giữ chỗ…" : "Chọn chuyến"}
        <ArrowRight size={15} />
      </button>
    </article>
  );
}
