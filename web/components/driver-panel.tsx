"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import useSWR from "swr";
import {
  ArrowRight,
  CalendarDays,
  CarFront,
  Check,
  Clock3,
  Flag,
  MapPin,
  Navigation,
  RefreshCw,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import { fetcher, mutate } from "@/lib/api";
import { serverNow, useServerNow } from "@/lib/server-clock";
import { LocationDetails } from "./location-details";
import {
  dateTime,
  humanStatus,
  localDateInput,
  money,
  serviceNames,
} from "@/lib/format";
import {
  rows,
  type Booking,
  type JsonObject,
  type ListResponse,
  type Offer,
  type PoolTrip,
  type RidePlan,
} from "@/lib/types";
import {
  EmptyState,
  ErrorNotice,
  Loading,
  Metric,
  SectionTitle,
  SubmitButton,
} from "./ui";
import { places } from "./trip-form";

export function DriverPanel() {
  const {
    data: offers,
    error: offersError,
    mutate: refreshOffers,
  } = useSWR<ListResponse<Offer>>("/offers", fetcher, {
    refreshInterval: 3000,
    shouldRetryOnError: false,
  });
  const {
    data: rides,
    error: ridesError,
    mutate: refreshRides,
  } = useSWR<ListResponse<RidePlan>>("/driver/rides", fetcher, {
    refreshInterval: 4000,
    shouldRetryOnError: false,
  });
  const { data: earnings, error: earningsError } = useSWR<JsonObject>(
    "/driver/earnings",
    fetcher,
    { refreshInterval: 10000, shouldRetryOnError: false },
  );
  const [actionError, setActionError] = useState<unknown>();
  const [pending, setPending] = useState<string | null>(null);
  async function action(path: string, body: JsonObject = {}) {
    setPending(path);
    setActionError(undefined);
    try {
      await mutate(path, body);
      await Promise.all([refreshOffers(), refreshRides()]);
    } catch (caught) {
      setActionError(caught);
    } finally {
      setPending(null);
    }
  }
  return (
    <div className="view-stack">
      <SectionTitle
        eyebrow="DÀNH CHO TÀI XẾ"
        title="Hôm nay, bạn đi đâu?"
        description="Quản lý nhận chuyến, hành trình đang chạy và thu nhập của bạn."
      />
      <div className="driver-summary">
        <Metric
          label="Tổng thực nhận"
          value={money(
            earnings?.total_driver_payout_vnd ?? earnings?.total_vnd,
          )}
          note="Theo các chuyến đã đối soát"
        />
        <Metric
          label="Bù từ Quỹ bảo đảm"
          value={money(
            earnings?.guarantee_total_vnd ?? earnings?.guarantee_vnd,
          )}
          note="Tách riêng với cước chuyến"
        />
        <Metric
          label="Offer đang chờ"
          value={
            offers
              ? rows(offers, "offers").filter(
                  (offer) => !offer.status || offer.status === "PENDING",
                ).length
              : "—"
          }
          note="Phản hồi trước khi hết hạn"
        />
      </div>
      <ErrorNotice error={actionError} />
      <div className="driver-columns">
        <div className="view-stack">
          <section className="surface">
            <SectionTitle
              title="Lời mời nhận chuyến"
              action={
                <button
                  className="icon-button"
                  aria-label="Làm mới offer"
                  onClick={() => void refreshOffers()}
                >
                  <RefreshCw size={15} />
                </button>
              }
            />
            <ErrorNotice error={offersError} />
            {!offers && !offersError && <Loading />}
            {offers &&
              rows(offers, "offers").filter(
                (offer) => !offer.status || offer.status === "PENDING",
              ).length === 0 && (
                <EmptyState
                  icon={<Navigation size={23} />}
                  title="Chưa có lời mời mới"
                >
                  Bật nhận chuyến và cập nhật vị trí để hệ thống tìm chuyến phù
                  hợp.
                </EmptyState>
              )}
            {rows(offers, "offers")
              .filter((offer) => !offer.status || offer.status === "PENDING")
              .map((offer) => (
                <div className="offer-card" key={offer.id}>
                  <div>
                    <h3>
                      {offer.service_code
                        ? serviceNames[offer.service_code]
                        : "Lời mời nhận chuyến"}
                    </h3>
                    <OfferCountdown expires={offer.expires_at} />
                  </div>
                  <div className="offer-route">
                    <LocationDetails point={offer.pickup} title="Điểm đón" />
                    <LocationDetails point={offer.dropoff} title="Điểm trả" />
                  </div>
                  <dl>
                    <div>
                      <dt>Mã booking</dt>
                      <dd>{offer.booking_id.slice(0, 8)}</dd>
                    </div>
                    {offer.estimated_driver_payout_vnd != null && (
                      <div>
                        <dt>
                          {offer.estimate_basis === "IF_MATCHED"
                            ? "Thu nhập dự kiến nếu ghép"
                            : "Thu nhập dự kiến"}
                        </dt>
                        <dd>{money(offer.estimated_driver_payout_vnd)}</dd>
                      </div>
                    )}
                    {offer.estimated_driver_hourly_vnd != null && (
                      <div>
                        <dt>Ước tính / giờ chở khách</dt>
                        <dd>{money(offer.estimated_driver_hourly_vnd)}</dd>
                      </div>
                    )}
                    {offer.duration_min != null && (
                      <div>
                        <dt>Thời gian chở khách</dt>
                        <dd>
                          {Math.round(offer.duration_min)} phút ·{" "}
                          {offer.distance_km?.toFixed(1)} km
                        </dd>
                      </div>
                    )}
                    {offer.pickup_time && (
                      <div>
                        <dt>Giờ đón dự kiến</dt>
                        <dd>
                          {dateTime(offer.pickup_time)} · {offer.seat_count}{" "}
                          khách
                        </dd>
                      </div>
                    )}
                    {offer.unmatched_driver_payout_vnd != null && (
                      <div>
                        <dt>Nếu không ghép, theo chính sách bảo đảm</dt>
                        <dd>{money(offer.unmatched_driver_payout_vnd)}</dd>
                      </div>
                    )}
                  </dl>
                  <p className="hint">
                    Ước tính thu nhập chưa trừ chi phí vận hành; tiền cuối cùng
                    theo kết quả chuyến.
                  </p>
                  <div className="button-row">
                    <button
                      className="primary"
                      disabled={pending !== null}
                      onClick={() => void action(`/offers/${offer.id}/accept`)}
                    >
                      <Check size={16} />
                      Nhận chuyến
                    </button>
                    <button
                      className="secondary"
                      disabled={pending !== null}
                      onClick={() =>
                        void action(`/offers/${offer.id}/reject`, {
                          reason_code: "DRIVER_UNAVAILABLE",
                        })
                      }
                    >
                      Từ chối
                    </button>
                  </div>
                </div>
              ))}
          </section>
          <section className="surface">
            <SectionTitle title="Hành trình đang điều hành" />
            <ErrorNotice error={ridesError} />
            {rides && rows(rides, "plans").length === 0 && (
              <EmptyState
                icon={<CarFront size={24} />}
                title="Bạn chưa có chuyến đang chạy"
              >
                Các chuyến được xác nhận sẽ hiển thị tại đây.
              </EmptyState>
            )}
            {rows(rides, "plans").map((ride) => (
              <RideCard
                key={ride.id}
                ride={ride}
                pending={pending !== null}
                onAction={action}
              />
            ))}
          </section>
          <section className="surface">
            <SectionTitle title="Chi tiết thu nhập" />
            <ErrorNotice error={earningsError} />
            <EarningsTable data={earnings} />
          </section>
        </div>
        <DriverSettings />
      </div>
      <IntercityDriver />
    </div>
  );
}

function OfferCountdown({ expires }: { expires?: string }) {
  const now = useServerNow();
  if (!expires)
    return (
      <span className="badge neutral">
        <Clock3 size={12} />
        Chờ phản hồi
      </span>
    );
  const remaining = Math.max(0, Math.ceil((Date.parse(expires) - now) / 1000));
  return (
    <span className={`badge ${remaining < 6 ? "warning" : "neutral"}`}>
      <Clock3 size={12} />
      {remaining > 0 ? `Còn ${remaining} giây` : "Đã hết hạn"}
    </span>
  );
}

function RideCard({
  ride,
  pending,
  onAction,
}: {
  ride: RidePlan;
  pending: boolean;
  onAction: (path: string, body?: JsonObject) => Promise<void>;
}) {
  const [incident, setIncident] = useState(false);
  const [reason, setReason] = useState("VEHICLE_BREAKDOWN");
  const now = useServerNow();
  const bookingStatuses =
    ride.bookings?.map((booking: Booking) => booking.ride_status) ?? [];
  const journeyStarted = Boolean(ride.started) || ride.status === "DEPARTED";
  const startable = !journeyStarted && bookingStatuses.includes("CONFIRMED");
  const deposited = ride.bookings
    ?.filter((b) => b.ride_status === "CONFIRMED")
    .every((b) =>
      ["DEPOSITED", "LOCKED", "TOPPED_UP"].includes(b.escrow_status),
    );
  const canStart =
    (ride.can_start ?? Boolean(deposited)) &&
    (!ride.departure_time || now >= Date.parse(ride.departure_time));
  const running = bookingStatuses.includes("RIDE_STARTED");
  const allFinished =
    bookingStatuses.length > 0 &&
    bookingStatuses.every((status) =>
      [
        "COMPLETED",
        "CANCELLED_BY_PASSENGER",
        "CANCELLED_BY_DRIVER",
        "CANCELLED_BY_SYSTEM",
        "NO_SHOW",
        "EXPIRED",
      ].includes(status),
    );
  const currentStop = ride.stops?.findIndex((stop) => !stop.completed) ?? -1;
  return (
    <article className="ride-card">
      <div className="ride-header">
        <span className="service-icon pool">
          <CarFront size={20} />
        </span>
        <div>
          <h3>
            {ride.service_code ? serviceNames[ride.service_code] : "Chuyến đi"}
          </h3>
          <small>
            {ride.id.slice(0, 8)} · {humanStatus(ride.status)}
          </small>
        </div>
      </div>
      <ol className="stop-list">
        {ride.stops?.map((stop, index) => (
          <li
            key={stop.id}
            className={
              stop.completed ? "done" : index === currentStop ? "current" : ""
            }
          >
            <span className="stop-dot">
              {stop.completed ? <Check size={11} /> : index + 1}
            </span>
            <div>
              <strong>
                {(stop.kind ?? stop.stop_type) === "PICKUP"
                  ? "Đón khách"
                  : "Trả khách"}
              </strong>
              <small>Booking {stop.booking_id?.slice(0, 8) ?? "—"}</small>
              <LocationDetails point={stop.point} />
            </div>
            {index === currentStop && (
              <button
                className="text-button"
                disabled={pending || !journeyStarted}
                onClick={() =>
                  void onAction(`/rides/${ride.id}/stops/${stop.id}/complete`)
                }
              >
                Xác nhận <ArrowRight size={13} />
              </button>
            )}
          </li>
        ))}
      </ol>
      {ride.bookings?.map((booking) => (
        <div className="ride-booking" key={booking.id}>
          <span>Booking {booking.id.slice(0, 8)}</span>
          <strong>{humanStatus(booking.escrow_status)}</strong>
          {booking.ride_status === "CONFIRMED" && (
            <>
              <button
                className="text-button"
                disabled={pending}
                onClick={() =>
                  void onAction(`/rides/${ride.id}/arrived`, {
                    booking_id: booking.id,
                  })
                }
              >
                Đã đến điểm đón
              </button>
              <button
                className="text-button danger-text"
                disabled={
                  pending ||
                  !booking.no_show_eligible_at ||
                  now < booking.no_show_eligible_at * 1000
                }
                onClick={() => void onAction(`/bookings/${booking.id}/no-show`)}
              >
                Khách không đến · Chờ đủ 5 phút
              </button>
            </>
          )}
          {booking.price_status === "POOL_SEARCHING" &&
            ride.bookings &&
            ride.bookings.length > 1 && (
              <button
                className="text-button danger-text"
                disabled={pending}
                onClick={() =>
                  void onAction(
                    `/rides/${ride.id}/coriders/${booking.id}/decline`,
                    { reason_code: "DRIVER_DECLINED" },
                  )
                }
              >
                Từ chối ghép · Cắt bảo đảm
              </button>
            )}
        </div>
      ))}
      <div className="button-row">
        {startable && !canStart && (
          <p className="hint ride-readiness">
            {!deposited
              ? "Đang chờ xác nhận ký quỹ trước khi khởi hành."
              : ride.departure_time && now < Date.parse(ride.departure_time)
                ? `Khởi hành từ ${dateTime(ride.departure_time)}. Vui lòng chờ đến giờ.`
                : "Đang chờ chốt thứ tự đón và cập nhật điều kiện khởi hành."}
          </p>
        )}
        {startable && (
          <button
            className="primary"
            disabled={pending || !canStart}
            onClick={() => void onAction(`/rides/${ride.id}/start`)}
          >
            <Navigation size={15} />
            Bắt đầu chuyến
          </button>
        )}
        {(running || allFinished) && (
          <button
            className="primary"
            disabled={pending || !allFinished}
            onClick={() => void onAction(`/rides/${ride.id}/complete`)}
          >
            <Flag size={15} />
            Hoàn thành chuyến
          </button>
        )}
        <button
          className="text-button danger-text"
          onClick={() => setIncident(!incident)}
        >
          Báo sự cố
        </button>
      </div>
      {incident && (
        <div className="incident-form">
          <label>
            Lý do sự cố
            <select
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            >
              <option value="VEHICLE_BREAKDOWN">Phương tiện gặp sự cố</option>
              <option value="SAFETY_ISSUE">Lo ngại an toàn</option>
              <option value="MEDICAL_EMERGENCY">
                Tình huống y tế khẩn cấp
              </option>
            </select>
          </label>
          <p>
            Hệ thống sẽ hủy các booking bị ảnh hưởng và hoàn ký quỹ theo chính
            sách.
          </p>
          <button
            className="danger-button"
            disabled={pending}
            onClick={() =>
              void onAction(`/rides/${ride.id}/abort`, { reason_code: reason })
            }
          >
            Xác nhận dừng chuyến
          </button>
        </div>
      )}
    </article>
  );
}

type DriverSettingFields = {
  online: boolean;
  accepts_urban: boolean;
  pool_enabled: boolean;
  accepts_intercity: boolean;
  max_driver_detour_km: number;
  max_driver_detour_min: number;
  max_additional_pickups: number;
};

function DriverSettings() {
  const {
    data,
    error,
    isLoading,
    mutate: refresh,
  } = useSWR<JsonObject>("/driver/settings", fetcher, {
    shouldRetryOnError: false,
  });
  const [actionError, setActionError] = useState<unknown>();
  const [notice, setNotice] = useState("");
  const [location, setLocation] = useState({ lat: 20.9612, lon: 105.7473 });
  const {
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting, dirtyFields },
  } = useForm<DriverSettingFields>({
    resetOptions: { keepDirtyValues: true },
    values: {
      online: Boolean(data?.online ?? data?.is_online),
      accepts_urban: Boolean(data?.accepts_urban ?? true),
      pool_enabled: Boolean(data?.pool_enabled),
      accepts_intercity: Boolean(data?.accepts_intercity),
      max_driver_detour_km: Number(data?.max_driver_detour_km ?? 10),
      max_driver_detour_min: Number(data?.max_driver_detour_min ?? 20),
      max_additional_pickups: Number(data?.max_additional_pickups ?? 3),
    },
  });
  const hasUnsavedChanges = Object.keys(dirtyFields).length > 0;
  async function save(fields: DriverSettingFields) {
    setActionError(undefined);
    setNotice("");
    try {
      await mutate("/driver/settings", fields, "PUT");
      await refresh();
      reset(fields);
      setNotice("Đã cập nhật cấu hình nhận chuyến.");
    } catch (caught) {
      setActionError(caught);
    }
  }
  async function updateLocation() {
    setActionError(undefined);
    try {
      await mutate("/driver/location", location, "PUT");
      setNotice("Đã cập nhật vị trí tài xế.");
    } catch (caught) {
      setActionError(caught);
    }
  }
  if (!data)
    return (
      <aside className="surface driver-settings">
        <SectionTitle title="Cấu hình nhận chuyến" />
        {isLoading ? (
          <Loading label="Đang tải cấu hình nhận chuyến…" />
        ) : (
          <ErrorNotice error={error} retry={() => void refresh()} />
        )}
      </aside>
    );
  return (
    <aside className="surface driver-settings">
      <SectionTitle title="Cấu hình nhận chuyến" />
      <div className="kyc-status">
        <ShieldCheck size={20} />
        <div>
          <strong>{humanStatus(String(data?.kyc_status ?? "NONE"))}</strong>
          <small>
            {data?.vehicle_type === "BIKE"
              ? "Xe máy · 1 hành khách"
              : "Taxi · 4 ghế hành khách"}
          </small>
        </div>
      </div>
      <ErrorNotice error={error} />
      <ErrorNotice error={actionError} />
      {notice && (
        <p className="success-text" role="status">
          {notice}
        </p>
      )}
      <form onSubmit={handleSubmit(save)}>
        {hasUnsavedChanges && (
          <p className="hint" role="status">
            Bạn có thay đổi chưa lưu.
          </p>
        )}
        <label className="toggle-field">
          <span>
            Trực tuyến<small>Sẵn sàng nhận chuyến mới</small>
          </span>
          <input type="checkbox" {...register("online")} />
        </label>
        <label className="toggle-field">
          <span>Nhận chuyến nội đô</span>
          <input type="checkbox" {...register("accepts_urban")} />
        </label>
        <label className="toggle-field">
          <span>
            Cho phép ghép nội đô<small>Yêu cầu KYC đã xác minh</small>
          </span>
          <input type="checkbox" {...register("pool_enabled")} />
        </label>
        <label className="toggle-field">
          <span>
            Nhận liên tỉnh<small>Yêu cầu KYC đã xác minh</small>
          </span>
          <input type="checkbox" {...register("accepts_intercity")} />
        </label>
        <div className="form-grid two">
          <label>
            Đi vòng tối đa (km)
            <input
              type="number"
              min="0"
              max="50"
              {...register("max_driver_detour_km", { valueAsNumber: true })}
            />
          </label>
          <label>
            Đi vòng tối đa (phút)
            <input
              type="number"
              min="0"
              max="120"
              {...register("max_driver_detour_min", { valueAsNumber: true })}
            />
          </label>
        </div>
        <label>
          Điểm đón phát sinh tối đa
          <select
            {...register("max_additional_pickups", { valueAsNumber: true })}
          >
            {[0, 1, 2, 3].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <SubmitButton pending={isSubmitting}>Lưu cấu hình</SubmitButton>
      </form>
      <hr />
      <h3 className="small-heading">
        <MapPin size={16} />
        Vị trí hiện tại
      </h3>
      <div className="form-grid two">
        <label>
          Vĩ độ
          <input
            type="number"
            step="any"
            value={location.lat}
            onChange={(event) =>
              setLocation({ ...location, lat: Number(event.target.value) })
            }
          />
        </label>
        <label>
          Kinh độ
          <input
            type="number"
            step="any"
            value={location.lon}
            onChange={(event) =>
              setLocation({ ...location, lon: Number(event.target.value) })
            }
          />
        </label>
      </div>
      <button className="secondary" onClick={() => void updateLocation()}>
        Cập nhật vị trí
      </button>
      <p className="hint">
        Nhập tọa độ hoặc dùng vị trí được cấp trong kịch bản demo.
      </p>
    </aside>
  );
}

type PublishFields = {
  corridor_id: string;
  departure_time: string;
  min_seats_to_run: number;
  seat_price_vnd: string;
  destination_index: number;
};

function IntercityDriver() {
  const {
    data,
    error,
    mutate: refresh,
  } = useSWR<ListResponse<PoolTrip>>("/driver/pool-trips", fetcher, {
    refreshInterval: 10000,
    shouldRetryOnError: false,
  });
  const [actionError, setActionError] = useState<unknown>();
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<PublishFields>({
    defaultValues: {
      corridor_id: "HN_HADONG__HY_TP",
      departure_time: localDateInput(new Date(serverNow() + 5 * 86400000)),
      min_seats_to_run: 3,
      seat_price_vnd: "",
      destination_index: 4,
    },
  });
  async function publish(fields: PublishFields) {
    setActionError(undefined);
    const origin = places[0];
    const dest = places[fields.destination_index];
    try {
      await mutate("/driver/pool-trips", {
        corridor_id: fields.corridor_id,
        origin: { lat: origin.lat, lon: origin.lon },
        destination: { lat: dest.lat, lon: dest.lon },
        departure_time: new Date(fields.departure_time).toISOString(),
        departure_flex_min: 30,
        min_seats_to_run: fields.min_seats_to_run,
        ...(fields.seat_price_vnd
          ? { seat_price_vnd: Number(fields.seat_price_vnd) }
          : {}),
      });
      await refresh();
    } catch (caught) {
      setActionError(caught);
    }
  }
  async function decide(id: string, decision: "RUN" | "CANCEL") {
    setActionError(undefined);
    try {
      await mutate(`/driver/pool-trips/${id}/under-min-decision`, { decision });
      await refresh();
    } catch (caught) {
      setActionError(caught);
    }
  }
  return (
    <section className="surface">
      <SectionTitle
        eyebrow="HÀNH TRÌNH XA HƠN"
        title="Chuyến ghép liên tỉnh"
        description="Đăng chuyến từ 3–7 ngày trước giờ đi. Giá ghế được kiểm tra theo khung ±10% giá tham chiếu."
      />
      <ErrorNotice error={error} />
      <ErrorNotice error={actionError} />
      <div className="intercity-columns">
        <form onSubmit={handleSubmit(publish)} className="publish-form">
          <h3>
            <CalendarDays size={18} />
            Đăng lịch chuyến mới
          </h3>
          <label>
            Hành lang tuyến
            <input
              required
              maxLength={80}
              {...register("corridor_id", { required: true })}
            />
          </label>
          <label>
            Điểm đến
            <select {...register("destination_index", { valueAsNumber: true })}>
              <option value={4}>TP Hưng Yên</option>
              <option value={5}>TP Bắc Ninh</option>
            </select>
          </label>
          <small className="hint">Điểm đầu: Đại học Phenikaa, Hà Đông</small>
          <label>
            Ngày, giờ khởi hành
            <input
              type="datetime-local"
              required
              {...register("departure_time", { required: true })}
            />
          </label>
          <div className="form-grid two">
            <label>
              Ngưỡng khởi hành
              <select
                {...register("min_seats_to_run", { valueAsNumber: true })}
              >
                <option value={3}>3 ghế</option>
                <option value={2}>2 ghế</option>
              </select>
            </label>
            <label>
              Giá ghế (VND)
              <input
                type="number"
                step="1000"
                min="1000"
                placeholder="Theo tham chiếu"
                {...register("seat_price_vnd")}
              />
            </label>
          </div>
          <SubmitButton pending={isSubmitting}>Đăng chuyến</SubmitButton>
        </form>
        <div className="pool-trip-list">
          {rows(data, "trips").length === 0 && (
            <EmptyState
              icon={<CalendarDays size={24} />}
              title="Chưa có lịch chuyến"
            >
              Đăng chuyến đầu tiên để hành khách đặt ghế trước ngày đi.
            </EmptyState>
          )}
          {rows(data, "trips").map((trip) => (
            <article className="pool-trip-card" key={trip.id}>
              <span className="badge neutral">{humanStatus(trip.status)}</span>
              <h3>{trip.corridor_id.replaceAll("_", " ")}</h3>
              <p>
                {dateTime(trip.departure_time)} · {trip.seats_booked}/
                {trip.seats_total ?? 4} ghế đã đặt
              </p>
              <div className="pool-trip-price">
                <strong>{money(trip.seat_price_vnd)}</strong>
                <span>/ ghế · Chạy từ {trip.min_seats_to_run} ghế</span>
              </div>
              {trip.status === "UNDER_MIN_DRIVER_DECISION" && (
                <div className="button-row">
                  <button
                    className="primary"
                    onClick={() => void decide(trip.id, "RUN")}
                  >
                    Chạy dưới ngưỡng
                  </button>
                  <button
                    className="secondary"
                    onClick={() => void decide(trip.id, "CANCEL")}
                  >
                    Hủy và hoàn tiền
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function EarningsTable({ data }: { data: JsonObject | undefined }) {
  if (!data) return <p className="hint">Chưa có dữ liệu đối soát.</p>;
  const items = rows(data as ListResponse<JsonObject>, "payouts");
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Booking</th>
            <th>Cước thực thu</th>
            <th>Tài xế từ cước</th>
            <th>Quỹ chi bù</th>
            <th>Tổng thực nhận</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={5} className="table-empty">
                Chưa có chuyến đã đối soát.
              </td>
            </tr>
          ) : (
            items.map((item, index) => (
              <tr key={String(item.id ?? item.booking_id ?? index)}>
                <td>{String(item.booking_id ?? "—").slice(0, 8)}</td>
                <td>{money(item.gross_fare_charged_vnd)}</td>
                <td>{money(item.driver_base_amount_vnd)}</td>
                <td>{money(item.guarantee_amount_vnd)}</td>
                <td className="amount">
                  {money(item.total_driver_payout_vnd)}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
