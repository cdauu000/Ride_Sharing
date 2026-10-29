"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  BarChart3,
  Check,
  CircleDollarSign,
  FlaskConical,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { fetcher, mutate } from "@/lib/api";
import { dateTime, humanStatus, money } from "@/lib/format";
import { rows, type JsonObject, type ListResponse } from "@/lib/types";
import { EmptyState, ErrorNotice, Loading, Metric, SectionTitle } from "./ui";

type FundData = {
  balance_vnd: number;
  ledger: JsonObject[];
  p_actual_booking?: number | null;
  p_star_booking?: number | null;
  p_star_ride?: number | null;
  onchain_balance_vnd?: number | null;
  [key: string]: unknown;
};

export function AdminPanel() {
  const {
    data: metrics,
    error: metricsError,
    mutate: refreshMetrics,
  } = useSWR<JsonObject>("/admin/metrics", fetcher, {
    refreshInterval: 8000,
    shouldRetryOnError: false,
  });
  const {
    data: fund,
    error: fundError,
    mutate: refreshFund,
  } = useSWR<FundData>("/admin/fund", fetcher, {
    refreshInterval: 8000,
    shouldRetryOnError: false,
  });
  const {
    data: users,
    error: usersError,
    mutate: refreshUsers,
  } = useSWR<ListResponse<JsonObject>>("/admin/users", fetcher, {
    shouldRetryOnError: false,
  });
  const { data: trips, error: tripsError } = useSWR<ListResponse<JsonObject>>(
    "/admin/pool-trips",
    fetcher,
    { refreshInterval: 10000, shouldRetryOnError: false },
  );
  const [error, setError] = useState<unknown>();
  const [pending, setPending] = useState("");
  async function review(driver: JsonObject, status: "VERIFIED" | "REJECTED") {
    const id = String(driver.user_id ?? driver.id);
    setPending(id);
    setError(undefined);
    try {
      await mutate(`/admin/drivers/${id}/kyc-review`, { status });
      await refreshUsers();
    } catch (caught) {
      setError(caught);
    } finally {
      setPending("");
    }
  }
  const drivers = rows(users, "users").filter((user) => user.role === "DRIVER");
  return (
    <div className="view-stack">
      <SectionTitle
        eyebrow="TỔNG QUAN QUẢN TRỊ"
        title="Một hệ thống, mọi hành trình"
        description="Theo dõi vận hành, đối soát tài chính và chất lượng mô hình bằng dữ liệu đang có."
        action={
          <button
            className="text-button"
            onClick={() => {
              void refreshMetrics();
              void refreshFund();
            }}
          >
            <RefreshCw size={14} />
            Làm mới
          </button>
        }
      />
      <ErrorNotice error={metricsError} />
      <div className="admin-metrics">
        <Metric
          label="Tài xế trực tuyến"
          value={scalar(metrics, "active_drivers")}
        />
        <Metric
          label="Booking"
          value={scalar(
            metrics,
            "bookings",
            "bookings_count",
            "total_bookings",
          )}
        />
        <Metric
          label="Đã hoàn thành"
          value={
            typeof metrics?.bookings_by_status === "object" &&
            metrics.bookings_by_status
              ? String(
                  (metrics.bookings_by_status as JsonObject).COMPLETED ?? 0,
                )
              : scalar(metrics, "completed", "completed_bookings")
          }
        />
        <Metric
          label="Số dư Quỹ bảo đảm"
          value={money(fund?.balance_vnd)}
          note="Nguyên đồng Việt Nam"
        />
      </div>
      <section className="surface">
        <SectionTitle
          eyebrow="ĐỐI SOÁT QUỸ BẢO ĐẢM"
          title="Nhìn rõ từng dòng tiền"
          description="Khoản trích ghép thành công và khoản bù chuyến không ghép được được hạch toán riêng."
        />
        <ErrorNotice error={fundError} />
        {!fund && !fundError && <Loading />}
        {fund && (
          <>
            <div className="fund-overview">
              <div className="fund-balance">
                <CircleDollarSign size={22} />
                <span>
                  Số dư sổ cái<strong>{money(fund.balance_vnd)}</strong>
                  <small>
                    Số dư on-chain:{" "}
                    {fund.onchain_balance_vnd == null
                      ? "Chưa có bằng chứng đối soát"
                      : money(fund.onchain_balance_vnd)}
                  </small>
                </span>
              </div>
              <div className="fund-rates">
                <Rate
                  label="Tỷ lệ booking ghép thực tế"
                  value={fund.p_actual_booking}
                />
                <Rate
                  label="Hòa vốn theo booking"
                  value={fund.p_star_booking}
                />
                <Rate label="Hòa vốn theo chuyến" value={fund.p_star_ride} />
              </div>
            </div>
            <FundChart ledger={fund.ledger ?? []} />
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Thời điểm</th>
                    <th>Loại bút toán</th>
                    <th>Booking</th>
                    <th>Biến động</th>
                    <th>Số dư sau</th>
                  </tr>
                </thead>
                <tbody>
                  {(fund.ledger ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={5} className="table-empty">
                        Chưa có bút toán.
                      </td>
                    </tr>
                  ) : (
                    [...fund.ledger]
                      .reverse()
                      .slice(0, 50)
                      .map((entry, index) => (
                        <tr key={String(entry.id ?? index)}>
                          <td>{dateTime(entry.created_at)}</td>
                          <td>{entryLabel(String(entry.entry_type ?? ""))}</td>
                          <td>{String(entry.booking_id ?? "—").slice(0, 8)}</td>
                          <td
                            className={
                              Number(entry.amount_signed_vnd) >= 0
                                ? "success-text amount"
                                : "danger-text amount"
                            }
                          >
                            {Number(entry.amount_signed_vnd) > 0 ? "+" : ""}
                            {money(entry.amount_signed_vnd)}
                          </td>
                          <td className="amount">
                            {money(entry.balance_after_vnd)}
                          </td>
                        </tr>
                      ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
      <div className="admin-columns">
        <section className="surface">
          <SectionTitle eyebrow="XÁC MINH MÔ PHỎNG" title="Hồ sơ tài xế" />
          <ErrorNotice error={usersError} />
          <ErrorNotice error={error} />
          {drivers.length === 0 ? (
            <EmptyState
              icon={<ShieldCheck size={23} />}
              title="Chưa có hồ sơ tài xế"
            >
              Tài khoản tài xế đăng ký sẽ xuất hiện tại đây.
            </EmptyState>
          ) : (
            <div className="driver-review-list">
              {drivers.map((driver) => (
                <div
                  className="driver-review"
                  key={String(driver.id ?? driver.user_id)}
                >
                  <span className="avatar">
                    {String(driver.name ?? driver.email ?? "TX")
                      .slice(0, 2)
                      .toUpperCase()}
                  </span>
                  <div>
                    <strong>{String(driver.name ?? driver.email)}</strong>
                    <small>
                      {humanStatus(String(driver.kyc_status ?? "NONE"))}
                    </small>
                  </div>
                  <button
                    className="icon-button success-text"
                    aria-label={`Duyệt ${String(driver.name ?? driver.email)}`}
                    disabled={
                      pending !== "" || driver.kyc_status === "VERIFIED"
                    }
                    onClick={() => void review(driver, "VERIFIED")}
                  >
                    <Check size={18} />
                  </button>
                  <button
                    className="icon-button danger-text"
                    aria-label={`Từ chối ${String(driver.name ?? driver.email)}`}
                    disabled={
                      pending !== "" || driver.kyc_status === "REJECTED"
                    }
                    onClick={() => void review(driver, "REJECTED")}
                  >
                    <X size={17} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
        <section className="surface">
          <SectionTitle
            eyebrow="THEO DÕI LIÊN TỈNH"
            title="Các chuyến đã đăng"
          />
          <ErrorNotice error={tripsError} />
          <div className="compact-trip-list">
            {rows(trips, "trips").length === 0 && (
              <EmptyState
                icon={<Activity size={24} />}
                title="Chưa có chuyến liên tỉnh"
              >
                Tổng hợp trạng thái chốt chuyến tại T−72h và thứ tự đón T−24h.
              </EmptyState>
            )}
            {rows(trips, "trips")
              .slice(0, 12)
              .map((trip) => (
                <div key={String(trip.id)}>
                  <strong>
                    {String(trip.corridor_id ?? "Chuyến liên tỉnh").replaceAll(
                      "_",
                      " ",
                    )}
                  </strong>
                  <span>
                    {dateTime(trip.departure_time)} ·{" "}
                    {String(trip.seats_booked ?? 0)}/4 ghế
                  </span>
                  <small className="badge neutral">
                    {humanStatus(String(trip.status))}
                  </small>
                </div>
              ))}
          </div>
        </section>
      </div>
      <ModelAndJobPanel />
      <AdminResearch />
    </div>
  );
}

function scalar(data: JsonObject | undefined, ...keys: string[]): string {
  for (const key of keys)
    if (typeof data?.[key] === "number" || typeof data?.[key] === "string")
      return String(data[key]);
  return "—";
}

function Rate({
  label,
  value,
}: {
  label: string;
  value: number | null | undefined;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong>
        {value == null ? "Chưa đủ dữ liệu" : `${(value * 100).toFixed(1)}%`}
      </strong>
    </div>
  );
}

function entryLabel(type: string): string {
  return (
    {
      INITIAL_SEED: "Vốn mồi ban đầu",
      CONTRIBUTION: "Đóng góp ghép thành công",
      GUARANTEE_PAYOUT: "Chi bù bảo đảm",
      CANCEL_FEE_INFLOW: "Phí hủy nạp Quỹ",
    }[type] ?? type
  );
}

function FundChart({ ledger }: { ledger: JsonObject[] }) {
  const credits = ledger
    .filter(
      (entry) =>
        Number(entry.amount_signed_vnd) > 0 &&
        entry.entry_type !== "INITIAL_SEED",
    )
    .reduce((sum, entry) => sum + Number(entry.amount_signed_vnd), 0);
  const debits = -ledger
    .filter((entry) => Number(entry.amount_signed_vnd) < 0)
    .reduce((sum, entry) => sum + Number(entry.amount_signed_vnd), 0);
  const max = Math.max(credits, debits, 1);
  return (
    <div
      className="fund-chart"
      role="img"
      aria-label={`Tổng thu Quỹ: ${money(credits)}. Tổng chi Quỹ: ${money(debits)}.`}
    >
      <div>
        <span>
          <ArrowDownLeft size={15} />
          Thu từ vận hành
        </span>
        <div className="bar-track">
          <i style={{ width: `${(credits / max) * 100}%` }} />
        </div>
        <strong>{money(credits)}</strong>
      </div>
      <div>
        <span>
          <ArrowUpRight size={15} />
          Chi bảo đảm
        </span>
        <div className="bar-track expense">
          <i style={{ width: `${(debits / max) * 100}%` }} />
        </div>
        <strong>{money(debits)}</strong>
      </div>
    </div>
  );
}

function ModelAndJobPanel() {
  const [retryError, setRetryError] = useState<unknown>();
  const [retrying, setRetrying] = useState("");
  const { data: models, error: modelsError } = useSWR<
    JsonObject | JsonObject[]
  >("/admin/models", fetcher, { shouldRetryOnError: false });
  const {
    data: jobs,
    error: jobsError,
    mutate: refreshJobs,
  } = useSWR<ListResponse<JsonObject>>("/admin/jobs", fetcher, {
    refreshInterval: 6000,
    shouldRetryOnError: false,
  });
  const { data: batch, error: batchError } = useSWR<ListResponse<JsonObject>>(
    "/admin/batch-runs",
    fetcher,
    { refreshInterval: 10000, shouldRetryOnError: false },
  );
  const modelRows = Array.isArray(models)
    ? models
    : rows(models as ListResponse<JsonObject>, "models");
  async function retryJob(id: string) {
    setRetrying(id);
    setRetryError(undefined);
    try {
      await mutate(`/admin/jobs/${id}/retry`);
      await refreshJobs();
    } catch (caught) {
      setRetryError(caught);
    } finally {
      setRetrying("");
    }
  }
  return (
    <div className="view-stack">
      <section className="surface">
        <SectionTitle
          eyebrow="CHẤT LƯỢNG GỢI Ý"
          title="Mô hình & kiểm định"
          description="Điểm LTR chỉ có ý nghĩa xếp hạng. Xác suất chỉ được dùng sau khi hiệu chỉnh và kiểm định."
        />
        <ErrorNotice error={modelsError} />
        {modelRows.length === 0 ? (
          <EmptyState
            icon={<FlaskConical size={25} />}
            title="Chưa có mô hình đã đăng ký"
          >
            Gợi ý dùng Baseline cho đến khi có artifact hợp lệ. Kết quả huấn
            luyện và kiểm định phải được báo cáo riêng.
          </EmptyState>
        ) : (
          <div className="model-grid">
            {modelRows.map((model, index) => (
              <article
                className="model-card"
                key={String(model.id ?? model.version ?? index)}
              >
                <BarChart3 size={21} />
                <h3>{String(model.name ?? model.model_type ?? "Mô hình")}</h3>
                <span className="badge neutral">
                  {String(model.status ?? "Đã đăng ký")}
                </span>
                <p>{String(model.version ?? model.model_version ?? "")}</p>
                <dl>
                  {["ndcg_at_5", "hr_at_1", "brier_score", "ece"]
                    .filter(
                      (key) =>
                        model[key] != null ||
                        (typeof model.metrics === "object" &&
                          model.metrics &&
                          (model.metrics as JsonObject)[key] != null),
                    )
                    .map((key) => (
                      <div key={key}>
                        <dt>{key.toUpperCase().replaceAll("_", " ")}</dt>
                        <dd>
                          {Number(
                            model[key] ?? (model.metrics as JsonObject)?.[key],
                          ).toFixed(4)}
                        </dd>
                      </div>
                    ))}
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
      <section className="surface">
        <SectionTitle
          title="Tác vụ định thời"
          description="Theo dõi offer, ký quỹ và các mốc chốt chuyến bền vững trong cơ sở dữ liệu."
          action={
            <button className="text-button" onClick={() => void refreshJobs()}>
              <RefreshCw size={14} />
              Làm mới
            </button>
          }
        />
        <ErrorNotice error={jobsError} />
        <ErrorNotice error={retryError} />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Tác vụ</th>
                <th>Đến hạn</th>
                <th>Trạng thái</th>
                <th>Số lần thử</th>
              </tr>
            </thead>
            <tbody>
              {rows(jobs, "jobs").length === 0 ? (
                <tr>
                  <td colSpan={4} className="table-empty">
                    Chưa có tác vụ.
                  </td>
                </tr>
              ) : (
                rows(jobs, "jobs")
                  .slice(0, 40)
                  .map((job, index) => (
                    <tr key={String(job.id ?? index)}>
                      <td>{String(job.job_type)}</td>
                      <td>{dateTime(job.run_at)}</td>
                      <td>{humanStatus(String(job.status))}</td>
                      <td>
                        {String(job.attempts ?? 0)} /{" "}
                        {String(job.max_attempts ?? 5)}
                        {["DEAD_LETTER", "FAILED_RETRY"].includes(
                          String(job.status),
                        ) && (
                          <button
                            className="text-button"
                            disabled={retrying !== ""}
                            onClick={() => void retryJob(String(job.id))}
                          >
                            {retrying === job.id ? "Đang thử lại…" : "Thử lại"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      </section>
      <section className="surface">
        <SectionTitle
          title="Lịch sử ghép theo lô"
          description="Các phương án RTV được kiểm tra ràng buộc trước khi đưa vào bộ giải."
        />
        <ErrorNotice error={batchError} />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Lần chạy</th>
                <th>Bộ giải</th>
                <th>Trạng thái</th>
                <th>Được ghép</th>
                <th>Yêu cầu trong vòng</th>
              </tr>
            </thead>
            <tbody>
              {rows(batch, "runs").length === 0 ? (
                <tr>
                  <td colSpan={5} className="table-empty">
                    Chưa có vòng ghép theo lô.
                  </td>
                </tr>
              ) : (
                rows(batch, "runs")
                  .slice(0, 20)
                  .map((run, index) => (
                    <tr key={String(run.id ?? index)}>
                      <td>{String(run.id ?? "").slice(0, 8)}</td>
                      <td>{String(run.solver ?? "CP-SAT")}</td>
                      <td>{String(run.solver_status ?? run.status ?? "—")}</td>
                      <td>
                        {String(
                          run.assigned ??
                            run.matched_count ??
                            run.assigned_requests ??
                            "—",
                        )}
                      </td>
                      <td>{String(run.requests ?? "—")}</td>
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function AdminResearch() {
  const { data, error } = useSWR<JsonObject>("/admin/surveys", fetcher, {
    shouldRetryOnError: false,
  });
  return (
    <section className="surface">
      <SectionTitle
        eyebrow="NGHIÊN CỨU & KHẢO SÁT"
        title="Bằng chứng đi cùng sản phẩm"
        description="S1 cần 100–200 người trả lời thật, mỗi nhóm sinh viên và đi làm chiếm 40–60%. Dữ liệu mô phỏng được ghi nhãn riêng."
      />
      <ErrorNotice error={error} />
      <div className="research-summary">
        <Metric
          label="Phiếu khảo sát hợp lệ"
          value={scalar(data, "valid_respondents", "total_responses", "count")}
        />
        <Metric
          label="Sinh viên"
          value={scalar(data, "students", "student_count")}
        />
        <Metric
          label="Người đi làm"
          value={scalar(data, "workers", "worker_count")}
        />
      </div>
      <p className="inline-note">
        <FlaskConical size={15} />
        Không suy ra ý nghĩa thống kê khi chưa có đủ dữ liệu. Báo cáo H1–H11 cần
        kèm cỡ mẫu, seed, khoảng tin cậy và phiên bản cấu hình.
      </p>
    </section>
  );
}
