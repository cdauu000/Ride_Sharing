"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="standalone-error">
      <h1>Chưa thể hiển thị trang này</h1>
      <p>Hãy tải lại để kết nối lại với hệ thống.</p>
      <button className="primary" onClick={reset}>
        Thử lại
      </button>
    </main>
  );
}
