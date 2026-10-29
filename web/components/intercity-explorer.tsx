"use client";

import { useState } from "react";
import useSWR from "swr";
import { CalendarClock, CarFront, Route, UsersRound } from "lucide-react";
import { fetcher } from "@/lib/api";
import { dateTime, humanStatus, money } from "@/lib/format";
import { rows, type ListResponse, type PoolTrip } from "@/lib/types";
import { EmptyState, ErrorNotice, Loading, SectionTitle } from "./ui";

export function IntercityExplorer({ onPlanTrip }: { onPlanTrip: () => void }) {
  const [corridor, setCorridor] = useState("");
  const [date, setDate] = useState("");
  const [seats, setSeats] = useState(1);
  const params = new URLSearchParams({ seats: String(seats) });
  if (corridor) params.set("corridor", corridor);
  if (date) params.set("date", date);
  const { data, error, isLoading } = useSWR<ListResponse<PoolTrip>>(
    `/intercity/pool-trips?${params}`,
    fetcher,
    { shouldRetryOnError: false },
  );
  return (
    <section className="surface">
      <SectionTitle
        eyebrow="HẸN MỘT CHUYẾN ĐI XA"
        title="Khám phá ghép xe liên tỉnh"
        description="Các chuyến được tài xế đăng trước. Ghế được chốt theo ngưỡng khởi hành, có chính sách hoàn tiền rõ ràng."
      />
      <div className="explorer-filters">
        <label>
          Hành lang tuyến
          <input
            placeholder="Tất cả hành lang"
            value={corridor}
            onChange={(event) => setCorridor(event.target.value)}
          />
        </label>
        <label>
          Ngày khởi hành
          <input
            type="date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
          />
        </label>
        <label>
          Số ghế
          <select
            value={seats}
            onChange={(event) => setSeats(Number(event.target.value))}
          >
            {[1, 2, 3, 4].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
      </div>
      <ErrorNotice error={error} />
      {isLoading && <Loading />}
      <div className="explorer-list">
        {rows(data, "trips").map((trip) => (
          <article className="explorer-trip" key={trip.id}>
            <span className="service-icon pool">
              <Route size={24} />
            </span>
            <div>
              <span className="badge neutral">{humanStatus(trip.status)}</span>
              <h3>{trip.corridor_id.replaceAll("_", " ")}</h3>
              <p>
                <CalendarClock size={14} />
                {dateTime(trip.departure_time)}
              </p>
              <p>
                <UsersRound size={14} />
                {trip.seats_booked}/{trip.seats_total ?? 4} ghế · Chạy từ{" "}
                {trip.min_seats_to_run} ghế
              </p>
            </div>
            <div className="explorer-trip-price">
              <strong>{money(trip.seat_price_vnd)}</strong>
              <span>/ ghế, chưa gồm phụ phí ngoài vùng</span>
              <button className="secondary" onClick={onPlanTrip}>
                Chọn điểm đón, xem giá
              </button>
            </div>
          </article>
        ))}
      </div>
      {!isLoading && !error && rows(data, "trips").length === 0 && (
        <EmptyState
          icon={<CarFront size={25} />}
          title="Chưa có chuyến theo bộ lọc này"
        >
          Bạn có thể đổi ngày đi hoặc chọn taxi bao xe liên tỉnh để chủ động
          hơn.
        </EmptyState>
      )}
      <div className="intercity-help">
        <div>
          <strong>Cần đi ngay hoặc còn dưới 72 giờ?</strong>
          <p>
            Taxi bao xe liên tỉnh hỗ trợ đi ngay hoặc hẹn trước tối đa 7 ngày.
          </p>
        </div>
        <button className="text-button" onClick={onPlanTrip}>
          Tìm bao xe liên tỉnh →
        </button>
      </div>
    </section>
  );
}
