# Nội dung gói bàn giao local

Bản sau sửa lỗi nghiệm thu là **`artifacts/release/rise-sharing-revision9-local-v2.zip`**. Gói mới bổ sung các sửa lỗi, script khởi động review, hướng dẫn trực tiếp test và bằng chứng `uat-fixed-v4`; không chứa database, `.env` hoặc dependency đã cài. [Báo cáo kiểm thử lại](acceptance-retest-2026-10-28.md) là kết quả mới nhất. V1 được giữ nguyên để truy vết lịch sử.

Gói `artifacts/release/rise-sharing-revision9-local-v1.zip` chứa mã backend/frontend/research, hợp đồng Solidity và ABI, test, migration, cấu hình mẫu, bốn tài liệu gốc, tài liệu phân tích, model chính, dataset chính dạng Parquet, báo cáo và ảnh kiểm chứng. `release-manifest.json` trong gói ghi SHA-256 từng file; file `.zip.sha256` bên cạnh ghi hash của cả gói.

Không đóng gói `.env`, mật khẩu đã sinh, database vận hành, journal ví/ký quỹ, khóa riêng, mnemonic, `.venv` hoặc `node_modules`. Sau khi giải nén vào thư mục mới, cài dependency và chạy `init-demo` theo [README](../README.md) để sinh bí mật và tài khoản thử mới. Không sao chép dữ liệu demo cũ sang một môi trường có token thật.

Để tránh chứa hai bản dữ liệu giống nhau, archive chỉ kèm `artifacts/research/main_v1/observations.parquet`; JSONL đầy đủ vẫn nằm trong workspace hiện tại. CLI train đọc được cả Parquet và JSONL:

```powershell
.venv\Scripts\python.exe -m research train --dataset artifacts/research/main_v1/observations.parquet --output artifacts/models/retrained_new_version --version ltr_v9_retrained_new_version
```

Gói này là snapshot bản local đã kiểm chứng, chưa phải chứng nhận nghiệm thu toàn bộ MUST/SHOULD. Xem [verification.md](verification.md) và [requirements.md](requirements.md). Model và dữ liệu trong gói được gắn nhãn mô phỏng; chưa có dữ liệu khảo sát người thật và chưa có giao dịch testnet.
