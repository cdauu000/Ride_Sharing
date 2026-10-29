"use client";

import { useState } from "react";
import useSWR from "swr";
import { ClipboardCheck, CloudRain, GraduationCap } from "lucide-react";
import { fetcher, mutate } from "@/lib/api";
import { money, serviceNames } from "@/lib/format";
import type { ServiceCode } from "@/lib/types";
import { ErrorNotice, Loading, SectionTitle, SubmitButton } from "./ui";

type Alternative = {
  service_code: ServiceCode;
  price_vnd: number;
  pickup_min: number;
  duration_min: number;
  quote_vnd?: number;
  cap_vnd?: number;
  match_likelihood?: string;
  detour_ratio?: number;
  walk_m?: number;
};
type Scenario = {
  scenario_id: string;
  description: string;
  is_raining: boolean;
  alternatives: Alternative[];
};
type Instrument = {
  survey_version: string;
  scenarios: Scenario[];
  fairness_tables: Record<
    string,
    { passenger_a_vnd: number; passenger_b_vnd: number }
  >;
};
const orders = [
  ["proportional", "shapley", "inconvenience"],
  ["proportional", "inconvenience", "shapley"],
  ["shapley", "proportional", "inconvenience"],
  ["shapley", "inconvenience", "proportional"],
  ["inconvenience", "proportional", "shapley"],
  ["inconvenience", "shapley", "proportional"],
];

export function SurveyPanel() {
  const { data, error } = useSWR<Instrument>("/surveys/scenarios", fetcher, {
    shouldRetryOnError: false,
  });
  const [respondentId] = useState(() => {
    if (typeof window === "undefined") return "";
    const existing = window.localStorage.getItem(
      "chung-duong-survey-respondent",
    );
    if (
      existing &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        existing,
      )
    )
      return existing;
    const id = crypto.randomUUID();
    window.localStorage.setItem("chung-duong-survey-respondent", id);
    return id;
  });
  const [pending, setPending] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [actionError, setActionError] = useState<unknown>();
  const order = respondentId
    ? orders[Number(BigInt(`0x${respondentId.replaceAll("-", "")}`) % 6n)]
    : orders[0];
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data || !respondentId) return;
    const values = new FormData(event.currentTarget);
    setPending(true);
    setActionError(undefined);
    try {
      await mutate("/surveys/responses", {
        respondent_id: respondentId,
        survey_version: data.survey_version,
        segment: String(values.get("segment")),
        consent: values.get("consent") === "on",
        choices: data.scenarios.map((scenario) => ({
          scenario_id: scenario.scenario_id,
          selected_service: String(values.get(scenario.scenario_id)),
        })),
        fairness: Object.fromEntries(
          order.map((method) => [
            method,
            Number(values.get(`fairness_${method}`)),
          ]),
        ),
      });
      setSubmitted(true);
    } catch (caught) {
      setActionError(caught);
    } finally {
      setPending(false);
    }
  }
  if (submitted)
    return (
      <section className="surface survey-thanks">
        <ClipboardCheck size={44} />
        <h2>Đã ghi nhận lựa chọn của bạn</h2>
        <p>
          Cảm ơn bạn đã đóng góp cho nghiên cứu về di chuyển và chia sẻ chi phí.
          Câu trả lời được lưu với mã ngẫu nhiên, không gắn tên hoặc email.
        </p>
      </section>
    );
  return (
    <section className="surface survey-section">
      <SectionTitle
        eyebrow="KHẢO SÁT S1 · KHOẢNG 5 PHÚT"
        title="Bạn sẽ chọn cách đi nào?"
        description="Tám tình huống giả định và ba đánh giá cách chia tiền. Không có đáp án đúng hoặc sai. Không thu thập tên, email, số điện thoại hay mã sinh viên."
      />
      <ErrorNotice error={error} />
      {!data && !error && <Loading />}
      {data && (
        <form onSubmit={submit}>
          <div className="survey-consent">
            <GraduationCap size={22} />
            <div>
              <label>
                Bạn thuộc nhóm nào?
                <select name="segment" required defaultValue="">
                  <option value="" disabled>
                    Chọn nhóm khảo sát
                  </option>
                  <option value="STUDENT">Sinh viên</option>
                  <option value="WORKER">Người đi làm</option>
                </select>
              </label>
              <label className="checkbox">
                <input type="checkbox" name="consent" required />
                Tôi tự nguyện tham gia và đồng ý sử dụng câu trả lời ẩn danh cho
                nghiên cứu.
              </label>
              <small>
                Mã ngẫu nhiên được lưu trên trình duyệt chỉ để hạn chế trả lời
                trùng.
              </small>
            </div>
          </div>
          <div className="survey-scenarios">
            {data.scenarios.map((scenario, index) => (
              <fieldset key={scenario.scenario_id} className="survey-scenario">
                <legend>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {scenario.is_raining && <CloudRain size={17} />}{" "}
                  {scenario.description}
                </legend>
                <div className="survey-alternatives">
                  {scenario.alternatives.map((alternative) => (
                    <label
                      className="survey-choice"
                      key={alternative.service_code}
                    >
                      <input
                        type="radio"
                        required
                        name={scenario.scenario_id}
                        value={alternative.service_code}
                      />
                      <div>
                        <strong>
                          {serviceNames[alternative.service_code]}
                        </strong>
                        <b>{money(alternative.price_vnd)}</b>
                        <span>
                          Đón {alternative.pickup_min} phút · Đi{" "}
                          {alternative.duration_min} phút
                        </span>
                        {alternative.quote_vnd != null && (
                          <small>
                            Trần khi ghép: {money(alternative.quote_vnd)}
                            <br />
                            Không ghép: tối đa {money(alternative.cap_vnd)}
                          </small>
                        )}
                        {alternative.match_likelihood && (
                          <small>
                            Khả năng{" "}
                            {alternative.service_code === "CAR_INTERCITY_POOL"
                              ? "chuyến chạy"
                              : "ghép"}
                            : {alternative.match_likelihood}
                          </small>
                        )}
                        {alternative.detour_ratio != null && (
                          <small>
                            Đi vòng {alternative.detour_ratio * 100}% · Đi bộ{" "}
                            {alternative.walk_m ?? 0}m
                          </small>
                        )}
                      </div>
                    </label>
                  ))}
                  <label className="survey-choice outside">
                    <input
                      type="radio"
                      name={scenario.scenario_id}
                      value="OUTSIDE"
                    />
                    <div>
                      <strong>Phương tiện khác / không đi</strong>
                    </div>
                  </label>
                </div>
              </fieldset>
            ))}
          </div>
          <div className="fairness-section">
            <h3>Với bạn, cách chia tiền nào hợp lý?</h3>
            <p>
              Hai booking đi chung xe có tổng chi phí 248.500 đ trước làm tròn.
              Khách A đi thẳng 14 km, phải đi vòng thêm 25%. Khách B đi 9 km và
              không đi vòng. Giá bao xe riêng tương ứng: A 194.000 đ, B 133.000
              đ.
            </p>
            <p>
              Đánh giá từng phương án từ 1 (rất không hợp lý) đến 5 (rất hợp
              lý). Thứ tự phương án được đảo giữa các người trả lời.
            </p>
            <div className="fairness-grid">
              {order.map((method, index) => (
                <fieldset key={method} className="fairness-card">
                  <legend>Phương án {String.fromCharCode(65 + index)}</legend>
                  <div>
                    <span>Khách A trả</span>
                    <strong>
                      {money(data.fairness_tables[method]?.passenger_a_vnd)}
                    </strong>
                  </div>
                  <div>
                    <span>Khách B trả</span>
                    <strong>
                      {money(data.fairness_tables[method]?.passenger_b_vnd)}
                    </strong>
                  </div>
                  <div className="rating-options">
                    {[1, 2, 3, 4, 5].map((rating) => (
                      <label key={rating}>
                        <input
                          type="radio"
                          name={`fairness_${method}`}
                          value={rating}
                          required
                        />
                        <span>{rating}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              ))}
            </div>
          </div>
          <ErrorNotice error={actionError} />
          <SubmitButton pending={pending}>Gửi câu trả lời ẩn danh</SubmitButton>
        </form>
      )}
    </section>
  );
}
