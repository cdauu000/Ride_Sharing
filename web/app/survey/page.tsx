"use client";

import { SurveyPanel } from "@/components/survey-panel";

export default function PublicSurveyPage() {
  return (
    <main className="public-survey">
      <a className="brand-lockup" href="/">
        <span className="brand-mark">cđ</span>
        <span>
          chung đường<small>ĐI CÙNG NHAU, XA HƠN</small>
        </span>
      </a>
      <SurveyPanel />
      <a className="text-button" href="/">
        ← Về trang chủ
      </a>
    </main>
  );
}
