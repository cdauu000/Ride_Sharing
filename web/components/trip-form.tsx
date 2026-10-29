"use client";

import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import {
  ArrowDownUp,
  CalendarClock,
  ChevronDown,
  LocateFixed,
  Navigation,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { mutate } from "@/lib/api";
import type { Point, TripRequest } from "@/lib/types";
import { localDateInput } from "@/lib/format";
import { serverNow } from "@/lib/server-clock";
import { ErrorNotice, SubmitButton } from "./ui";
import { AddressField } from "./address-field";

const pointSignature = (point: Point) =>
  JSON.stringify([point.lat, point.lon, point.label]);

export const places: Point[] = [
  { lat: 20.961, lon: 105.747, label: "Đại học Phenikaa, Hà Đông" },
  { lat: 21.013, lon: 105.824, label: "Đống Đa, Hà Nội" },
  { lat: 20.983, lon: 105.731, label: "La Phù, Hoài Đức" },
  { lat: 20.995, lon: 105.807, label: "Nguyễn Trãi, Thanh Xuân" },
  { lat: 20.646, lon: 106.051, label: "TP Hưng Yên" },
  { lat: 21.1861, lon: 106.0763, label: "TP Bắc Ninh" },
];

type Fields = {
  booking_type: "NOW" | "SCHEDULED";
  vehicle_preference: "ANY" | "BIKE" | "CAR";
  ride_preference: "ANY" | "PRIVATE" | "POOL";
  passenger_count: number;
  has_luggage: boolean;
  budget_min: number;
  budget_max: number;
  preferred_departure: string;
  window_before: number;
  window_after: number;
  max_passenger_detour_ratio: number;
  is_raining: boolean;
  same_gender_coride: boolean;
};

export function TripForm({
  pickup,
  dropoff,
  onPickup,
  onDropoff,
  mapTarget,
  onMapTarget,
  onCreated,
  onIntentChange,
  onAddressPendingChange,
}: {
  pickup: Point;
  dropoff: Point;
  onPickup: (value: Point) => void;
  onDropoff: (value: Point) => void;
  mapTarget: "pickup" | "dropoff";
  onMapTarget: (target: "pickup" | "dropoff") => void;
  onCreated: (trip: TripRequest) => void;
  onIntentChange?: () => void;
  onAddressPendingChange?: (pending: boolean) => void;
}) {
  const [error, setError] = useState<unknown>();
  const [advanced, setAdvanced] = useState(false);
  const [geolocating, setGeolocating] = useState(false);
  const [drafts, setDrafts] = useState<{ pickup?: string; dropoff?: string }>(
    {},
  );
  const addressPending =
    drafts.pickup === pointSignature(pickup) ||
    drafts.dropoff === pointSignature(dropoff);
  useEffect(() => {
    onAddressPendingChange?.(addressPending);
  }, [addressPending, onAddressPendingChange]);
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { isSubmitting },
  } = useForm<Fields>({
    defaultValues: {
      booking_type: "NOW",
      vehicle_preference: "ANY",
      ride_preference: "ANY",
      passenger_count: 1,
      has_luggage: false,
      budget_min: 80000,
      budget_max: 800000,
      preferred_departure: localDateInput(new Date(serverNow() + 3600000)),
      window_before: 15,
      window_after: 30,
      max_passenger_detour_ratio: 0.3,
      is_raining: false,
      same_gender_coride: false,
    },
  });
  const bookingType = watch("booking_type");
  const signature = JSON.stringify({ pickup, dropoff, fields: watch() });
  const latestSignature = useRef(signature);
  latestSignature.current = signature;
  const revision = useRef(0);
  function invalidate() {
    revision.current += 1;
    onIntentChange?.();
  }
  async function submit(fields: Fields) {
    invalidate();
    const submittedRevision = revision.current;
    const submittedSignature = latestSignature.current;
    setError(undefined);
    if (
      drafts.pickup === pointSignature(pickup) ||
      drafts.dropoff === pointSignature(dropoff)
    ) {
      setError(
        new Error(
          "Vui lòng tìm và chọn địa chỉ cho điểm đón/đến đang nhập, hoặc chọn vị trí trên bản đồ.",
        ),
      );
      return;
    }
    if (fields.budget_min > fields.budget_max) {
      setError(
        new Error(
          "Ngân sách mong muốn cần nhỏ hơn hoặc bằng ngân sách tối đa.",
        ),
      );
      return;
    }
    if (pickup.lat === dropoff.lat && pickup.lon === dropoff.lon) {
      setError(new Error("Điểm đón và điểm đến cần khác nhau."));
      return;
    }
    try {
      const { window_before, window_after, ...data } = fields;
      const payload: Record<string, unknown> = {
        ...data,
        pickup: { lat: pickup.lat, lon: pickup.lon },
        dropoff: { lat: dropoff.lat, lon: dropoff.lon },
        pickup_label: pickup.label,
        dropoff_label: dropoff.label,
        max_walk_m: 0,
      };
      if (fields.booking_type === "SCHEDULED") {
        const time = new Date(fields.preferred_departure).getTime();
        if (!Number.isFinite(time) || time <= serverNow())
          throw new Error("Vui lòng chọn thời gian khởi hành trong tương lai.");
        payload.preferred_departure = new Date(time).toISOString();
        payload.earliest_departure = new Date(
          time - Number(window_before) * 60000,
        ).toISOString();
        payload.latest_departure = new Date(
          time + Number(window_after) * 60000,
        ).toISOString();
      } else delete payload.preferred_departure;
      const result = await mutate<TripRequest>("/trip-requests", payload);
      if (
        submittedRevision === revision.current &&
        submittedSignature === latestSignature.current
      )
        onCreated(result);
    } catch (caught) {
      if (
        submittedRevision === revision.current &&
        submittedSignature === latestSignature.current
      )
        setError(caught);
    }
  }
  function locate() {
    if (!navigator.geolocation) {
      setError(
        new Error(
          "Trình duyệt chưa hỗ trợ định vị. Vui lòng chọn trên bản đồ.",
        ),
      );
      return;
    }
    setGeolocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        onPickup({
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          label: "Vị trí hiện tại",
        });
        setGeolocating(false);
      },
      () => {
        setGeolocating(false);
        setError(
          new Error(
            "Không lấy được vị trí. Bạn có thể chọn trên bản đồ hoặc nhập tọa độ.",
          ),
        );
      },
      { timeout: 10000, enableHighAccuracy: true, maximumAge: 0 },
    );
  }
  return (
    <form
      className="trip-form"
      onChangeCapture={invalidate}
      onSubmit={handleSubmit(submit)}
    >
      <div className="segmented">
        <button
          type="button"
          className={bookingType === "NOW" ? "active" : ""}
          onClick={() => {
            invalidate();
            setValue("booking_type", "NOW");
          }}
        >
          <Navigation size={15} />
          Đi ngay
        </button>
        <button
          type="button"
          className={bookingType === "SCHEDULED" ? "active" : ""}
          onClick={() => {
            invalidate();
            setValue("booking_type", "SCHEDULED");
          }}
        >
          <CalendarClock size={15} />
          Hẹn trước
        </button>
      </div>
      <div className="route-inputs">
        <AddressField
          label="Điểm đón"
          point={pickup}
          onChange={onPickup}
          active={mapTarget === "pickup"}
          onFocus={() => onMapTarget("pickup")}
          letter="A"
          presets={places}
          onEdit={(pending) => {
            setDrafts((current) => ({
              ...current,
              pickup: pending ? pointSignature(pickup) : undefined,
            }));
            invalidate();
          }}
        />
        <button
          type="button"
          className="swap-button icon-button"
          aria-label="Đổi điểm đón và điểm đến"
          onClick={() => {
            onPickup(dropoff);
            onDropoff(pickup);
          }}
        >
          <ArrowDownUp size={16} />
        </button>
        <AddressField
          label="Điểm đến"
          point={dropoff}
          onChange={onDropoff}
          active={mapTarget === "dropoff"}
          onFocus={() => onMapTarget("dropoff")}
          letter="B"
          presets={places}
          onEdit={(pending) => {
            setDrafts((current) => ({
              ...current,
              dropoff: pending ? pointSignature(dropoff) : undefined,
            }));
            invalidate();
          }}
        />
      </div>
      <button
        type="button"
        className="text-button location-button"
        onClick={locate}
        disabled={geolocating}
      >
        <LocateFixed size={14} />
        {geolocating ? "Đang xác định vị trí…" : "Dùng vị trí hiện tại"}
      </button>
      {bookingType === "SCHEDULED" && (
        <div className="schedule-fields">
          <label>
            Ngày và giờ đi
            <input
              type="datetime-local"
              required
              {...register("preferred_departure")}
            />
          </label>
          <div className="form-grid two">
            <label>
              Có thể đón sớm (phút)
              <input
                type="number"
                min="0"
                max="120"
                {...register("window_before", { valueAsNumber: true })}
              />
            </label>
            <label>
              Có thể đón muộn (phút)
              <input
                type="number"
                min="0"
                max="120"
                {...register("window_after", { valueAsNumber: true })}
              />
            </label>
          </div>
          <p className="hint">
            Ghép liên tỉnh cần đặt trước từ 72 giờ đến 7 ngày.
          </p>
        </div>
      )}
      <div className="form-grid two">
        <label>
          Số hành khách
          <select {...register("passenger_count", { valueAsNumber: true })}>
            {[1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>
                {n} người
              </option>
            ))}
          </select>
        </label>
        <label>
          Phương tiện
          <select {...register("vehicle_preference")}>
            <option value="ANY">Bất kỳ</option>
            <option value="BIKE">Xe máy</option>
            <option value="CAR">Taxi</option>
          </select>
        </label>
      </div>
      <div className="form-grid two">
        <label>
          Ngân sách mong muốn
          <input
            type="number"
            min="0"
            step="1000"
            {...register("budget_min", { valueAsNumber: true, required: true })}
          />
        </label>
        <label>
          Tối đa có thể trả
          <input
            type="number"
            min="1000"
            step="1000"
            {...register("budget_max", { valueAsNumber: true, required: true })}
          />
        </label>
      </div>
      <div className="check-row">
        <label className="checkbox">
          <input type="checkbox" {...register("has_luggage")} />
          Hành lý lớn
        </label>
        <label className="checkbox">
          <input type="checkbox" {...register("is_raining")} />
          Trời đang mưa
        </label>
      </div>
      <button
        type="button"
        className="advanced-toggle"
        aria-expanded={advanced}
        onClick={() => setAdvanced(!advanced)}
      >
        <SlidersHorizontal size={15} />
        Tùy chọn hành trình
        <ChevronDown size={15} className={advanced ? "rotate" : ""} />
      </button>
      {advanced && (
        <div className="advanced-fields">
          <label>
            Hình thức đi
            <select {...register("ride_preference")}>
              <option value="ANY">Bao xe hoặc đi ghép</option>
              <option value="PRIVATE">Chỉ bao xe</option>
              <option value="POOL">Chỉ đi ghép</option>
            </select>
          </label>
          <label>
            Đi vòng tối đa
            <select
              {...register("max_passenger_detour_ratio", {
                valueAsNumber: true,
              })}
            >
              <option value="0.1">10%</option>
              <option value="0.2">20%</option>
              <option value="0.3">30%</option>
            </select>
          </label>
          <label className="checkbox">
            <input type="checkbox" {...register("same_gender_coride")} />
            Chỉ ghép với hành khách cùng giới tính đã xác minh
          </label>
        </div>
      )}
      <ErrorNotice error={error} />
      <SubmitButton pending={isSubmitting}>
        <Search size={17} />
        {isSubmitting ? "Đang tìm lựa chọn phù hợp…" : "Tìm chuyến phù hợp"}
      </SubmitButton>
      <p className="form-footnote">
        Bạn sẽ được xem giá và xác nhận trước khi đặt.
      </p>
    </form>
  );
}
