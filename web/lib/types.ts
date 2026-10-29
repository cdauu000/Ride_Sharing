export type Role = "PASSENGER" | "DRIVER" | "ADMIN";
export type ServiceCode =
  | "BIKE_URBAN"
  | "CAR_URBAN_PRIVATE"
  | "CAR_URBAN_POOL"
  | "CAR_INTERCITY_PRIVATE"
  | "CAR_INTERCITY_POOL";
export type Point = {
  lat: number;
  lon: number;
  label?: string;
  source?: string | null;
  precision?: "reference" | null;
};
export type RoadRoute = {
  distance_m: number;
  duration_s: number;
  geometry: { type: "LineString"; coordinates: [number, number][] };
  waypoints: { location: [number, number]; distance_m: number }[];
  profile: "car";
  attribution: string;
};
export type JsonObject = Record<string, unknown>;
export type User = {
  id: string;
  name?: string;
  full_name?: string;
  email: string;
  role: Role;
};
export type SystemInfo = {
  routing_mode?: string;
  escrow_mode?: string;
  database?: string;
  pricing_version?: string;
  app_version?: string;
  [key: string]: unknown;
};
export type TripRequest = {
  id: string;
  mode: string;
  allowed_service_codes: ServiceCode[];
  rejection_reasons?: Record<string, string | string[]>;
  [key: string]: unknown;
};
export type Candidate = {
  id: string;
  service_code: ServiceCode;
  driver_id?: string;
  source_type?: string;
  estimated_price?: number;
  fare_matched_est_vnd?: number;
  pool_quote_price_vnd?: number;
  pool_unmatched_price_vnd?: number;
  quoted_price_cap_vnd?: number;
  fare_vnd?: number;
  expected_price_vnd?: number;
  planned_pickup_eta_min?: number;
  pickup_eta_min?: number;
  in_vehicle_duration_min?: number;
  duration_min?: number;
  direct_distance_km?: number;
  detour_ratio?: number;
  p_match_est?: number;
  score?: number;
  labels?: string[];
  [key: string]: unknown;
};
export type RecommendationRun = {
  id?: string;
  run_id?: string;
  request_id?: string;
  candidates?: Candidate[];
  items?: Candidate[];
  [key: string]: unknown;
};
export type Booking = {
  pickup?: Point;
  dropoff?: Point;
  no_show_eligible_at?: number | null;
  id: string;
  service_code: ServiceCode;
  ride_status: string;
  price_status: string;
  escrow_status: string;
  quoted_price_cap_vnd?: number;
  pool_quote_price_vnd?: number;
  current_estimated_price_vnd?: number;
  final_price_vnd?: number | null;
  cancellation_fee_vnd?: number;
  ride_plan_id?: string;
  scheduled_trip_id?: string;
  driver_id?: string;
  stops?: Stop[];
  offer?: Offer;
  [key: string]: unknown;
};
export type Offer = {
  pickup?: Point;
  dropoff?: Point;
  seat_count?: number;
  pickup_time?: string;
  duration_min?: number;
  distance_km?: number;
  estimated_driver_payout_vnd?: number;
  estimated_driver_hourly_vnd?: number;
  unmatched_driver_payout_vnd?: number | null;
  estimate_basis?: string;
  id: string;
  booking_id: string;
  service_code?: ServiceCode;
  expires_at?: string;
  status?: string;
  [key: string]: unknown;
};
export type Stop = {
  id: string;
  booking_id?: string;
  kind?: string;
  stop_type?: string;
  point?: Point;
  completed?: boolean;
  [key: string]: unknown;
};
export type RidePlan = {
  started?: boolean;
  can_start?: boolean;
  departure_time?: string | null;
  id: string;
  service_code?: ServiceCode;
  status?: string;
  stops?: Stop[];
  bookings?: Booking[];
  [key: string]: unknown;
};
export type PoolTrip = {
  id: string;
  corridor_id: string;
  departure_time: string;
  seats_total?: number;
  seats_booked: number;
  min_seats_to_run: number;
  seat_price_vnd: number;
  status: string;
  [key: string]: unknown;
};
export type ListResponse<T> =
  | T[]
  | {
      items?: T[];
      bookings?: T[];
      offers?: T[];
      plans?: T[];
      trips?: T[];
      entries?: T[];
      [key: string]: unknown;
    };

export function rows<T>(
  value: ListResponse<T> | undefined,
  key = "items",
): T[] {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  const found = value[key] ?? value.items;
  return Array.isArray(found) ? (found as T[]) : [];
}
