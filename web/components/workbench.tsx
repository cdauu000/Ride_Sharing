"use client";

import { useState } from "react";
import useSWR, { SWRConfig, useSWRConfig } from "swr";
import {
  ArrowUpRight,
  Bike,
  CalendarDays,
  ChevronRight,
  CircleHelp,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  MapPinned,
  Menu,
  ShieldCheck,
  Sparkles,
  UsersRound,
  X,
} from "lucide-react";
import { api, ApiError, fetcher, mutate } from "@/lib/api";
import type {
  Booking,
  Point,
  SystemInfo,
  TripRequest,
  User,
} from "@/lib/types";
import { AuthPanel } from "./auth-panel";
import { AdminPanel } from "./admin-panel";
import { Bookings } from "./bookings";
import { DriverPanel } from "./driver-panel";
import { IntercityExplorer } from "./intercity-explorer";
import { Recommendations } from "./recommendations";
import { JourneyMap } from "./journey-map";
import { SurveyPanel } from "./survey-panel";
import { TripForm, places } from "./trip-form";
import { ErrorNotice, Loading } from "./ui";

type Tab = "plan" | "bookings" | "intercity" | "driver" | "admin" | "survey";
const navigation = [
  { id: "plan" as const, label: "Tìm chuyến", icon: MapPinned },
  { id: "bookings" as const, label: "Hành trình của tôi", icon: ClipboardList },
  { id: "intercity" as const, label: "Khám phá liên tỉnh", icon: CalendarDays },
  { id: "driver" as const, label: "Dành cho tài xế", icon: UsersRound },
  { id: "admin" as const, label: "Quản trị vận hành", icon: LayoutDashboard },
  { id: "survey" as const, label: "Khảo sát nghiên cứu", icon: CircleHelp },
];

export function Workbench() {
  return (
    <SWRConfig
      value={{ fetcher, shouldRetryOnError: false, revalidateOnFocus: false }}
    >
      <WorkbenchContent />
    </SWRConfig>
  );
}

function WorkbenchContent() {
  const { mutate: resetCache } = useSWRConfig();
  const {
    data: user,
    error: authError,
    isLoading,
    mutate: refreshUser,
  } = useSWR<User>("/auth/me", fetcher, { shouldRetryOnError: false });
  const { data: system } = useSWR<SystemInfo>("/system", fetcher, {
    refreshInterval: 30000,
    shouldRetryOnError: false,
  });
  const [selectedTab, setTab] = useState<Tab | null>(null);
  const tab =
    selectedTab ??
    (user?.role === "DRIVER"
      ? "driver"
      : user?.role === "ADMIN"
        ? "admin"
        : "plan");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [trip, setTrip] = useState<TripRequest | null>(null);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [pickup, setPickup] = useState<Point>(places[0]);
  const [dropoff, setDropoff] = useState<Point>(places[1]);
  const [mapTarget, setMapTarget] = useState<"pickup" | "dropoff">("pickup");
  const [addressPending, setAddressPending] = useState(false);
  const [logoutError, setLogoutError] = useState<unknown>();
  function go(next: Tab) {
    setTab(next);
    setSidebarOpen(false);
  }
  async function logout() {
    try {
      await mutate("/auth/logout");
      setTrip(null);
      setBooking(null);
      setTab(null);
      await resetCache(
        (key) =>
          typeof key === "string" && key !== "/auth/me" && key !== "/system",
        undefined,
        { revalidate: false },
      );
      await refreshUser(undefined, { revalidate: true });
    } catch (error) {
      setLogoutError(error);
    }
  }
  function authenticated(value: User) {
    void resetCache(
      (key) =>
        typeof key === "string" && key !== "/auth/me" && key !== "/system",
      undefined,
      { revalidate: false },
    );
    void refreshUser(value, { revalidate: false });
    setTab(
      value.role === "DRIVER"
        ? "driver"
        : value.role === "ADMIN"
          ? "admin"
          : "plan",
    );
  }
  if (isLoading)
    return (
      <div className="page-loading">
        <span className="brand-mark">cđ</span>
        <Loading label="Đang kết nối với hành trình của bạn…" />
      </div>
    );
  if (!user || (authError instanceof ApiError && authError.status === 401))
    return (
      <>
        <AuthPanel onAuthenticated={authenticated} />
        {authError &&
          (!(authError instanceof ApiError) || authError.status !== 401) && (
            <div className="connection-notice">
              <ErrorNotice error={authError} retry={() => void refreshUser()} />
            </div>
          )}
        <footer className="login-footer">
          Revision 9 · Nguyên mẫu nghiên cứu đa dịch vụ · Chưa vận hành thương
          mại
        </footer>
      </>
    );
  const current = navigation.find((item) => item.id === tab);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Bỏ qua điều hướng
      </a>
      {sidebarOpen && (
        <button
          className="sidebar-overlay"
          aria-label="Đóng điều hướng"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <a
          href="#"
          className="brand-lockup"
          onClick={(event) => {
            event.preventDefault();
            go("plan");
          }}
        >
          <span className="brand-mark">cđ</span>
          <span>
            chung đường<small>ĐI CÙNG NHAU, XA HƠN</small>
          </span>
        </a>
        <button
          className="sidebar-close icon-button"
          aria-label="Đóng điều hướng"
          onClick={() => setSidebarOpen(false)}
        >
          <X size={20} />
        </button>
        <span className="sidebar-label">BÀN LÀM VIỆC</span>
        <nav aria-label="Điều hướng chính">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={tab === item.id ? "active" : ""}
              aria-current={tab === item.id ? "page" : undefined}
              onClick={() => go(item.id)}
            >
              <item.icon size={19} />
              {item.label}
              {tab === item.id && <ChevronRight size={15} />}
            </button>
          ))}
        </nav>
        <div className="sidebar-story">
          <Sparkles size={21} />
          <p>
            Những chuyến đi tốt hơn
            <br />
            bắt đầu từ lựa chọn rõ ràng.
          </p>
          <span>5 dịch vụ · 1 hành trình</span>
        </div>
        <div className="sidebar-user">
          <span className="avatar">
            {(user.name ?? user.email).slice(0, 2).toUpperCase()}
          </span>
          <div>
            <strong>{user.name ?? user.email.split("@")[0]}</strong>
            <small>
              {user.role === "PASSENGER"
                ? "Hành khách"
                : user.role === "DRIVER"
                  ? "Tài xế"
                  : "Quản trị viên"}
            </small>
          </div>
          <button
            className="icon-button"
            aria-label="Đăng xuất"
            onClick={() => void logout()}
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="mobile-menu icon-button"
              aria-label="Mở điều hướng"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu size={21} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={12} />
            <strong>{current?.label}</strong>
          </div>
          <div className="topbar-right">
            <span className="research-tag">
              <span className="live-dot" />
              Nguyên mẫu nghiên cứu
            </span>
            <span className="topbar-location">
              Hà Nội, Việt Nam <ArrowUpRight size={13} />
            </span>
          </div>
        </header>
        <main id="main-content">
          <ErrorNotice error={logoutError} />
          <SystemBanner system={system} />
          {tab === "plan" && (
            <>
              <div className="page-intro">
                <div>
                  <span className="eyebrow">
                    CHÀO {user.name?.split(" ").at(-1)?.toUpperCase() ?? "BẠN"},
                    MÌNH ĐI THÔI
                  </span>
                  <h1>
                    Đi theo cách của bạn<span>.</span>
                  </h1>
                  <p>Một điểm đến. Nhiều lựa chọn. Mức giá luôn rõ ràng.</p>
                </div>
                <div className="intro-stamp">
                  <span>
                    <Bike size={18} />
                    <UsersRound size={18} />
                  </span>
                  <small>Nội đô đến liên tỉnh</small>
                </div>
              </div>
              <section className="planner-layout">
                <div className="surface planner-form">
                  <div className="planner-heading">
                    <span className="section-number">01</span>
                    <div>
                      <h2>Lên lịch hành trình</h2>
                      <p>Bạn muốn đi từ đâu đến đâu?</p>
                    </div>
                  </div>
                  <TripForm
                    pickup={pickup}
                    dropoff={dropoff}
                    onPickup={(point) => {
                      setTrip(null);
                      setPickup(point);
                    }}
                    onDropoff={(point) => {
                      setTrip(null);
                      setDropoff(point);
                    }}
                    mapTarget={mapTarget}
                    onMapTarget={setMapTarget}
                    onCreated={setTrip}
                    onIntentChange={() => setTrip(null)}
                    onAddressPendingChange={setAddressPending}
                  />
                </div>
                <div className="planner-map">
                  <JourneyMap
                    pickup={pickup}
                    dropoff={dropoff}
                    target={mapTarget}
                    pending={addressPending}
                    pricingFixture={system?.routing_mode === "fixture"}
                    onPick={(point, target) => {
                      setTrip(null);
                      return (target ?? mapTarget) === "pickup"
                        ? setPickup(point)
                        : setDropoff(point);
                    }}
                  />
                  <div className="map-bottom">
                    <span>
                      <ShieldCheck size={18} />
                      <strong>Biết giá trước khi đặt</strong>
                      <small>Quỹ bảo đảm & ký quỹ theo booking</small>
                    </span>
                    <span className="map-coordinates">
                      {pickup.lat.toFixed(4)}° N<br />
                      {pickup.lon.toFixed(4)}° E
                    </span>
                  </div>
                </div>
              </section>
              <Recommendations
                key={trip?.id ?? "no-current-search"}
                trip={trip}
                onBooked={(value) => {
                  setBooking(value);
                  go("bookings");
                }}
              />
            </>
          )}
          {tab === "bookings" && (
            <Bookings
              selected={booking}
              onUpdated={() => {
                if (booking)
                  void api<Booking>(`/bookings/${booking.id}`)
                    .then(setBooking)
                    .catch(() => undefined);
              }}
            />
          )}{" "}
          {tab === "intercity" && (
            <IntercityExplorer
              onPlanTrip={() => {
                setDropoff(places[4]);
                go("plan");
              }}
            />
          )}{" "}
          {tab === "driver" &&
            (user.role === "DRIVER" ? (
              <DriverPanel />
            ) : (
              <RoleNotice role="tài xế" />
            ))}{" "}
          {tab === "admin" &&
            (user.role === "ADMIN" ? (
              <>
                <AdminPanel />
                {system?.escrow_mode === "local" && <LocalDemoControls />}
              </>
            ) : (
              <RoleNotice role="quản trị viên" />
            ))}{" "}
          {tab === "survey" && <SurveyPanel />}
          <footer className="workspace-footer">
            <span>
              chung đường <b>·</b> Revision 9
            </span>
            <span>Nguyên mẫu nghiên cứu · Không sử dụng tiền thật</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

function RoleNotice({ role }: { role: string }) {
  return (
    <section className="surface role-notice">
      <ShieldCheck size={35} />
      <h2>Khu vực dành cho {role}</h2>
      <p>
        Tài khoản hiện tại chưa có quyền truy cập. Đăng xuất và đăng nhập bằng
        tài khoản {role} để tiếp tục.
      </p>
    </section>
  );
}

function SystemBanner({ system }: { system: SystemInfo | undefined }) {
  if (!system) return null;
  const fixture = system.routing_mode === "fixture";
  const local = system.escrow_mode === "local";
  if (!fixture && !local)
    return (
      <div className="system-banner connected">
        <span className="live-dot" />
        Định tuyến OSRM · Ký quỹ EVM theo cấu hình mạng
      </div>
    );
  return (
    <div className="system-banner">
      <ShieldCheck size={15} />
      <span>
        Môi trường thử nghiệm
        {fixture ? " · Định tuyến bằng dữ liệu fixture" : " · Định tuyến OSRM"}
        {local
          ? " · Ký quỹ sổ cái cục bộ, chưa có giao dịch testnet"
          : " · Ký quỹ EVM"}
      </span>
    </div>
  );
}

function LocalDemoControls() {
  const [seconds, setSeconds] = useState(86400);
  const [error, setError] = useState<unknown>();
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);
  async function run(path: string, body: Record<string, unknown>) {
    setPending(true);
    setError(undefined);
    setNotice("");
    try {
      await mutate(path, body);
      setNotice("Đã thực hiện. Làm mới các bảng để xem trạng thái mới.");
    } catch (caught) {
      setError(caught);
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="surface local-demo">
      <h3>Điều khiển kịch bản cục bộ</h3>
      <p>
        Dùng đồng hồ mô phỏng để kiểm tra mốc T−72h, T−60h và T−24h. Chỉ khả
        dụng trong môi trường local.
      </p>
      <ErrorNotice error={error} />
      {notice && (
        <p className="success-text" role="status">
          {notice}
        </p>
      )}
      <div className="button-row">
        <button
          className="secondary"
          disabled={pending}
          onClick={() => void run("/admin/jobs/run", {})}
        >
          Chạy các job đến hạn
        </button>
        <label>
          Tiến đồng hồ (giây)
          <input
            type="number"
            min="0"
            step="3600"
            max="604800"
            value={seconds}
            onChange={(event) => setSeconds(Number(event.target.value))}
          />
        </label>
        <button
          className="secondary"
          disabled={pending}
          onClick={() =>
            void run("/admin/demo-clock", { advance_seconds: seconds })
          }
        >
          Tiến thời gian demo
        </button>
      </div>
    </section>
  );
}
