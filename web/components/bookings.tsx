"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  BellRing,
  CircleCheck,
  Clock3,
  ReceiptText,
  RefreshCw,
  Share2,
  Shield,
  Siren,
  Wallet,
} from "lucide-react";
import { fetcher, mutate } from "@/lib/api";
import { dateTime, humanStatus, money, serviceNames } from "@/lib/format";
import {
  rows,
  type Booking,
  type JsonObject,
  type ListResponse,
} from "@/lib/types";
import { EmptyState, ErrorNotice, Loading, SectionTitle } from "./ui";
import { LocationDetails } from "./location-details";

const terminal = new Set([
  "COMPLETED",
  "EXPIRED",
  "CANCELLED_BY_PASSENGER",
  "CANCELLED_BY_DRIVER",
  "CANCELLED_BY_SYSTEM",
  "NO_SHOW",
]);

export function Bookings({
  selected,
  onUpdated,
}: {
  selected: Booking | null;
  onUpdated: () => void;
}) {
  const {
    data,
    error,
    isLoading,
    mutate: refresh,
  } = useSWR<ListResponse<Booking>>("/bookings", fetcher, {
    refreshInterval: 4000,
    shouldRetryOnError: false,
  });
  const { data: topups, mutate: refreshTopups } = useSWR<
    ListResponse<JsonObject>
  >("/intercity/topup-offers", fetcher, {
    refreshInterval: 4000,
    shouldRetryOnError: false,
  });
  const bookings = rows(data, "bookings");
  const selectedInList = selected
    ? bookings.find((b) => b.id === selected.id)
    : undefined;
  const visible =
    selected && !selectedInList ? [selected, ...bookings] : bookings;
  return (
    <section>
      <SectionTitle
        eyebrow="HÀNH TRÌNH CỦA TÔI"
        title="Từ xác nhận đến điểm đến"
        description="Theo dõi hành trình, giá cuối cùng và ký quỹ tại cùng một nơi."
        action={
          <button className="text-button" onClick={() => void refresh()}>
            <RefreshCw size={14} />
            Làm mới
          </button>
        }
      />
      <ErrorNotice error={error} retry={() => void refresh()} />
      {isLoading && <Loading />}
      {!isLoading && visible.length === 0 && !error && (
        <EmptyState
          icon={<ReceiptText size={26} />}
          title="Chuyến đi của bạn sẽ xuất hiện ở đây"
        >
          Tìm và chọn chuyến phù hợp để bắt đầu.
        </EmptyState>
      )}
      <div className="booking-grid">
        {visible.map((booking) => (
          <BookingCard
            key={booking.id}
            booking={{
              ...booking,
              topup_offer: rows(topups).find(
                (offer) =>
                  offer.booking_id === booking.id && offer.status === "PENDING",
              ),
            }}
            highlighted={booking.id === selected?.id}
            onUpdated={() => {
              void refresh();
              void refreshTopups();
              onUpdated();
            }}
          />
        ))}
      </div>
    </section>
  );
}

function BookingCard({
  booking,
  highlighted,
  onUpdated,
}: {
  booking: Booking;
  highlighted: boolean;
  onUpdated: () => void;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState("");
  const [shareUrl, setShareUrl] = useState("");
  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const { data: breakdown, error: breakdownError } = useSWR<JsonObject>(
    breakdownOpen ? `/bookings/${booking.id}/price-breakdown` : null,
    fetcher,
    { shouldRetryOnError: false },
  );
  async function action(kind: string, body: JsonObject = {}) {
    setPending(true);
    setError(undefined);
    setNotice("");
    try {
      const response = await mutate<JsonObject>(
        `/bookings/${booking.id}/${kind}`,
        body,
      );
      if (kind === "share-link") {
        const raw = response.url ?? response.share_url;
        if (typeof raw === "string") {
          const url = new URL(raw, window.location.origin);
          if (
            ["http:", "https:"].includes(url.protocol) &&
            url.origin === window.location.origin
          )
            setShareUrl(url.toString());
          else
            setNotice(
              "Liên kết đã được tạo. Chỉ mở liên kết từ địa chỉ hệ thống đang sử dụng.",
            );
        } else if (typeof response.token === "string")
          setShareUrl(
            `${window.location.origin}/share/${encodeURIComponent(response.token)}`,
          );
      } else if (kind === "sos")
        setNotice(
          "Đã gửi cảnh báo SOS tới hệ thống quản trị. Đây là tính năng mô phỏng, không gọi dịch vụ cứu hộ.",
        );
      setCancelling(false);
      onUpdated();
    } catch (caught) {
      setError(caught);
    } finally {
      setPending(false);
    }
  }
  const active = !terminal.has(booking.ride_status);
  return (
    <article className={`booking-card ${highlighted ? "highlighted" : ""}`}>
      <div className="booking-heading">
        <div>
          <span className="eyebrow">BOOKING · {booking.id.slice(0, 8)}</span>
          <h3>{serviceNames[booking.service_code]}</h3>
        </div>
        <span
          className={`badge ${booking.ride_status === "COMPLETED" ? "success" : "neutral"}`}
        >
          {humanStatus(booking.ride_status)}
        </span>
      </div>
      <div className="booking-axes">
        <Axis
          icon={<Clock3 size={16} />}
          label="Hành trình"
          status={booking.ride_status}
        />
        <Axis
          icon={<ReceiptText size={16} />}
          label="Giá chuyến đi"
          status={booking.price_status}
        />
        <Axis
          icon={<Shield size={16} />}
          label="Ký quỹ"
          status={booking.escrow_status}
        />
      </div>
      <div className="booking-route">
        <LocationDetails point={booking.pickup} title="Điểm đón" />
        <LocationDetails point={booking.dropoff} title="Điểm trả" />
      </div>
      <div className="booking-money">
        <div>
          <span>
            {booking.final_price_vnd == null ? "Giá hiện tại" : "Giá đã khóa"}
          </span>
          <strong>
            {money(
              booking.final_price_vnd ?? booking.current_estimated_price_vnd,
            )}
          </strong>
        </div>
        <div>
          <span>Ký quỹ mức trần</span>
          <strong>{money(booking.quoted_price_cap_vnd)}</strong>
        </div>
      </div>
      {booking.escrow_status === "DEPOSIT_PENDING" && (
        <p className="inline-note">
          <Wallet size={14} />
          Đang chờ xác nhận ký quỹ. Chuyến chỉ khởi hành sau khi ký quỹ thành
          công.
        </p>
      )}
      {booking.price_status === "POOL_SEARCHING" && (
        <p className="inline-note">
          <BellRing size={14} />
          Đang mở tìm người đi cùng. Giá ghép được cập nhật khi có hành khách
          phù hợp.
        </p>
      )}
      <ErrorNotice error={error} />
      {notice && (
        <div className="notice success" role="status">
          <CircleCheck size={17} />
          <p>{notice}</p>
        </div>
      )}
      {shareUrl && (
        <div className="share-box">
          <label>
            Liên kết chia sẻ (có thời hạn)
            <input
              readOnly
              value={shareUrl}
              onFocus={(event) => event.target.select()}
            />
          </label>
          <a href={shareUrl} target="_blank" rel="noreferrer">
            Mở liên kết
          </a>
        </div>
      )}
      <div className="booking-actions">
        <button
          className="text-button"
          onClick={() => setBreakdownOpen(!breakdownOpen)}
        >
          <ReceiptText size={14} />
          {breakdownOpen ? "Ẩn chi tiết giá" : "Giải thích giá"}
        </button>
        {active && (
          <>
            <button
              className="text-button"
              disabled={pending}
              onClick={() => void action("share-link")}
            >
              <Share2 size={14} />
              Chia sẻ
            </button>
            <button
              className="text-button danger-text"
              disabled={pending}
              onClick={() =>
                void action("sos", {
                  reason_code: "PASSENGER_SOS",
                })
              }
            >
              <Siren size={14} />
              SOS mô phỏng
            </button>
            <button
              className="text-button"
              disabled={pending}
              onClick={() => setCancelling(!cancelling)}
            >
              Hủy chuyến
            </button>
          </>
        )}
      </div>
      {cancelling && (
        <div className="confirm-cancel">
          <p>
            Hủy chuyến sẽ áp dụng chính sách phí theo thời điểm. Phí được máy
            chủ tính và trừ từ ký quỹ.
          </p>
          <button
            className="danger-button"
            disabled={pending}
            onClick={() =>
              void action("cancel", { reason_code: "PASSENGER_REQUEST" })
            }
          >
            Xác nhận hủy chuyến
          </button>
          <button className="text-button" onClick={() => setCancelling(false)}>
            Tiếp tục hành trình
          </button>
        </div>
      )}
      {breakdownOpen && (
        <PriceBreakdown data={breakdown} error={breakdownError} />
      )}
      <TopupResponses booking={booking} onUpdated={onUpdated} />
      {booking.ride_status === "COMPLETED" && <RatingForm booking={booking} />}
    </article>
  );
}

function Axis({
  icon,
  label,
  status,
}: {
  icon: React.ReactNode;
  label: string;
  status: string;
}) {
  return (
    <div className="axis">
      <span>
        {icon}
        {label}
      </span>
      <strong>{humanStatus(status)}</strong>
    </div>
  );
}

function PriceBreakdown({
  data,
  error,
}: {
  data: JsonObject | undefined;
  error: unknown;
}) {
  if (error) return <ErrorNotice error={error} />;
  if (!data) return <Loading />;
  const labels: Record<string, string> = {
    private_fare_vnd: "Giá bao xe tham chiếu",
    private_fare_ref_vnd: "Giá bao xe tham chiếu",
    pool_quote_price_vnd: "Trần khi ghép được",
    quoted_price_cap_vnd: "Trần nghĩa vụ ký quỹ",
    current_estimated_price_vnd: "Giá dự kiến hiện tại",
    final_price_vnd: "Giá cuối cùng",
    floor_fare_vnd: "Cận dưới phân bổ",
    cap_fare_vnd: "Cận trên phân bổ",
    fare_exact_vnd: "Giá trước làm tròn",
    fare_charged_vnd: "Giá thực thu",
    rounding_absorbed_vnd: "Phần giảm do làm tròn",
    driver_base_amount_vnd: "Tài xế nhận từ cước",
    guarantee_amount_vnd: "Quỹ bảo đảm chi bù",
    total_driver_payout_vnd: "Tổng tài xế nhận",
    platform_net_amount_vnd: "Phí nền tảng",
    fund_contribution_vnd: "Đóng góp Quỹ bảo đảm",
    cancellation_fee_vnd: "Phí hủy",
    door_surcharge_vnd: "Phụ phí ngoài vùng",
  };
  const fare =
    typeof data.fare === "object" && data.fare ? (data.fare as JsonObject) : {};
  const settlement =
    typeof data.settlement === "object" && data.settlement
      ? (data.settlement as JsonObject)
      : {};
  const flattened: JsonObject = {
    ...data,
    fare_exact_vnd: fare.exact,
    fare_charged_vnd: fare.charged,
    rounding_absorbed_vnd: fare.rounding,
    floor_fare_vnd: fare.floor,
    cap_fare_vnd: fare.cap,
    ...settlement,
    ...(typeof data.participant === "object" && data.participant
      ? (data.participant as JsonObject)
      : {}),
    ...(typeof data.payout === "object" && data.payout
      ? (data.payout as JsonObject)
      : {}),
  };
  return (
    <div className="price-breakdown">
      <h4>Đối soát từng khoản tiền</h4>
      <dl>
        {Object.entries(labels)
          .filter(
            ([key]) => flattened[key] !== undefined && flattened[key] !== null,
          )
          .map(([key, label]) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd>{money(flattened[key])}</dd>
            </div>
          ))}
      </dl>
      {typeof data.explanation === "string" && <p>{data.explanation}</p>}
      {typeof data.pricing_version === "string" && (
        <small>Phiên bản giá: {data.pricing_version}</small>
      )}
    </div>
  );
}

function TopupResponses({
  booking,
  onUpdated,
}: {
  booking: Booking;
  onUpdated: () => void;
}) {
  const offer = booking.topup_offer;
  const [error, setError] = useState<unknown>();
  const [pending, setPending] = useState(false);
  if (typeof offer !== "object" || offer === null) return null;
  const item = offer as JsonObject;
  if (typeof item.id !== "string" || item.status !== "PENDING") return null;
  async function respond(response: "ACCEPT" | "DECLINE") {
    setPending(true);
    setError(undefined);
    try {
      await mutate(`/intercity/topup-offers/${item.id}/respond`, {
        decision: response,
      });
      onUpdated();
    } catch (caught) {
      setError(caught);
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="topup-card">
      <h4>Đề nghị góp thêm để chuyến khởi hành</h4>
      <p>
        Số tiền góp thêm:{" "}
        <strong>{money(item.topup_amount_vnd ?? item.amount_vnd)}</strong>. Bạn
        có quyền từ chối. Giá chỉ thay đổi khi bạn đồng ý và ký quỹ được nạp
        thêm.
      </p>
      {item.expires_at != null && (
        <p>Hạn phản hồi: {dateTime(item.expires_at)}</p>
      )}
      <ErrorNotice error={error} />
      <div className="button-row">
        <button
          className="primary"
          disabled={pending}
          onClick={() => void respond("ACCEPT")}
        >
          Đồng ý góp thêm
        </button>
        <button
          className="secondary"
          disabled={pending}
          onClick={() => void respond("DECLINE")}
        >
          Từ chối
        </button>
      </div>
    </div>
  );
}

function RatingForm({ booking }: { booking: Booking }) {
  const [score, setScore] = useState(5);
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>();
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(undefined);
    try {
      await mutate(`/bookings/${booking.id}/rating`, { score, comment });
      setDone(true);
    } catch (caught) {
      setError(caught);
    } finally {
      setPending(false);
    }
  }
  if (done)
    return (
      <p className="success-text rating-thanks" role="status">
        Đã ghi nhận đánh giá. Cảm ơn bạn đã chia sẻ trải nghiệm.
      </p>
    );
  return (
    <form className="rating-form" onSubmit={submit}>
      <h4>Hành trình này thế nào?</h4>
      <div className="rating-row">
        <label>
          Điểm đánh giá
          <select
            value={score}
            onChange={(event) => setScore(Number(event.target.value))}
          >
            {[5, 4, 3, 2, 1].map((value) => (
              <option key={value} value={value}>
                {value} / 5
              </option>
            ))}
          </select>
        </label>
        <label>
          Nhận xét (tùy chọn)
          <input
            maxLength={1000}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder="Chia sẻ trải nghiệm của bạn"
          />
        </label>
      </div>
      <ErrorNotice error={error} />
      <button className="secondary" disabled={pending}>
        Gửi đánh giá
      </button>
    </form>
  );
}
