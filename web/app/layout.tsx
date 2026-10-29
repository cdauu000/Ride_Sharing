import type { Metadata } from "next";
import type { ReactNode } from "react";
import "leaflet/dist/leaflet.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chung đường · Mỗi hành trình, thêm lựa chọn",
  description:
    "Bàn làm việc đặt xe đa dịch vụ, ghép chuyến minh bạch và đối soát ký quỹ theo Revision 9.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
