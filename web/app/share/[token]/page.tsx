"use client";

import { use } from "react";
import useSWR from "swr";
import { ArrowLeft, MapPin, ShieldCheck } from "lucide-react";
import { fetcher } from "@/lib/api";
import { humanStatus, serviceNames } from "@/lib/format";
import type { JsonObject, ServiceCode } from "@/lib/types";
import { ErrorNotice, Loading } from "@/components/ui";

export default function SharedJourney({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const { data, error, isLoading } = useSWR<JsonObject>(
    `/shared/${encodeURIComponent(token)}`,
    fetcher,
    { refreshInterval: 5000, shouldRetryOnError: false },
  );
  const booking =
    typeof data?.booking === "object" && data.booking
      ? (data.booking as JsonObject)
      : data;
  const service =
    typeof booking?.service_code === "string"
      ? serviceNames[booking.service_code as ServiceCode]
      : "Hành trình được chia sẻ";
  return (
    <main className="shared-journey">
      <a className="brand-lockup" href="/">
        <span className="brand-mark">cđ</span>
        <span>
          chung đường<small>ĐI CÙNG NHAU, XA HƠN</small>
        </span>
      </a>
      <section className="surface">
        <span className="eyebrow">CHIA SẺ HÀNH TRÌNH CÓ THỜI HẠN</span>
        <h1>{service}</h1>
        <p className="shared-intro">
          Người đi đã chủ động chia sẻ liên kết này để bạn theo dõi trạng thái
          hành trình.
        </p>
        <ErrorNotice error={error} />
        {isLoading && <Loading />}
        {booking && !error && (
          <div className="shared-status">
            <MapPin size={30} />
            <span>Trạng thái hiện tại</span>
            <strong>{humanStatus(String(booking.ride_status ?? ""))}</strong>
            {typeof booking.driver_name === "string" && (
              <small>Tài xế: {booking.driver_name}</small>
            )}
          </div>
        )}
        <p className="inline-note">
          <ShieldCheck size={15} />
          Liên kết chỉ cung cấp thông tin được phép chia sẻ và sẽ hết hạn. Không
          hiển thị thông tin riêng tư của hành khách đi cùng.
        </p>
      </section>
      <a className="text-button" href="/">
        <ArrowLeft size={15} />
        Về trang chủ
      </a>
    </main>
  );
}
