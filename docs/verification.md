# Báo cáo kiểm chứng và trạng thái bàn giao

Ngày tổng hợp: **28/10/2026**, theo múi giờ Việt Nam. Phạm vi đã chốt: **M1–M14 và S1–S9**; deploy bên ngoài được hoãn theo yêu cầu chủ dự án.

**Cập nhật sau sửa lỗi nghiệm thu:** [báo cáo kiểm thử lại](acceptance-retest-2026-10-28.md) ghi 31/31 UAT thật, 85 test toàn bộ Python và 1 test công cụ đối soát bổ sung, 15 unit frontend, 6 browser regression, 19 EVM. Bảng bên dưới giữ số liệu đợt bàn giao đầu; coverage cũ không được coi là coverage của mã vừa thay đổi.

## Các kiểm tra đã thực thi

| Kiểm tra | Kết quả | Bằng chứng / phạm vi |
|---|---|---|
| Python pytest | **79 đạt, 0 lỗi, 0 bỏ qua** | [JUnit](../artifacts/test-results.xml); giá, API, workflow, đồng thời SQLite, research, escrow và migration |
| Coverage pytest | **76,14%** (3.874/5.088 dòng thực thi) | [JSON pytest](../artifacts/unit-test-coverage.json); không bao gồm các CLI/adapter chạy riêng |
| Ruff lint + format | Đạt | `app research tests scripts migrations` |
| TypeScript | Đạt, không có lỗi kiểu | `npm.cmd --prefix web run typecheck` |
| Unit frontend | **10/10** | Vitest, 2 tệp |
| Browser UI mock | **4/4** | Hành khách, tài xế, Admin, mobile không tràn ngang |
| Browser backend thật | Đạt, `Runtime errors: []` | Đặt Bike → tài xế nhận → ký quỹ → đón/trả đúng thứ tự → hoàn tất → payout 64.800; đăng nhập ba vai trò |
| Next.js production build | Đạt | Next 16.4.3; `/`, `/survey`, `/share/[token]` |
| Prettier | Đạt | `app components lib tests` trong web |
| Solidity/EVM | **19/19** | Tiền nguyên, roles, partial topup/revert, refund, split, dispute, thiếu Quỹ nguyên tử |
| Python Web3 với EVM local thật | Đạt | 5 operation; retry/restart giữ cùng hash; tài xế 155.200, guarantee 7.300, Quỹ 4.992.700 |
| Migration | Đạt ở phạm vi đã chạy | Upgrade SQLite mới; biên dịch SQL PostgreSQL offline, chưa thực thi trên PostgreSQL |
| Phụ thuộc Python | Đạt | `pip check`: No broken requirements found |
| Audit npm production | **0 advisory** ở cả web và contracts | Audit lockfile hiện tại; không bao gồm dev toolchain |
| Quét mẫu secret trong mã ứng dụng | Không tìm thấy mẫu khóa riêng/`sk-…` | Không phải chứng nhận không có mọi loại bí mật hoặc lỗ hổng |

Ảnh thực tế: [hành khách](../artifacts/screenshots/passenger-live.png), [tài xế](../artifacts/screenshots/driver-live.png), [Admin](../artifacts/screenshots/admin-live.png).

Các kiểm thử quan trọng gồm 10.000 tổ hợp phân bổ sàn/trần/tổng; vector A+B và hai ghế; giá khách đã khóa; nhận offer thứ ba; 20 luồng tranh ghế cuối; no-show không trước cửa sổ đón; idempotency; webhook giả; export không rò rỉ. Góp thêm một phần bị từ chối phải hoàn tiền tăng thêm trước RUN giá cũ. RPC không rõ kết quả không được tự coi là thất bại đã hoàn tiền. Admin thử lại giữ nguyên operation ID và payload để tránh chi trùng.

Coverage chạy riêng các luồng nghiên cứu CLI và Python Web3 được tổng hợp vào [combined-coverage.json](../artifacts/combined-coverage.json): **85,69%** (4.360/5.088 dòng). Tệp này có phạm vi rộng hơn pytest; không dùng để thay đổi số đếm 79 ca pytest. Các artifact `verification_v1` là smoke kiểm chứng pipeline, không thay kết quả main.

## Kết quả hiệu năng và nghiên cứu

[Đo HTTP local](../artifacts/local_http_benchmark_v1.json): 30 mẫu, p50 54,66 ms, p95 77,36 ms; SQLite + routing fixture + Baseline, một client. **Chưa chứng minh SLA production/OSRM hoặc batch 500 yêu cầu trong 3 giây.**

Đã tạo dataset 50.000 yêu cầu/28 ngày, huấn luyện mô hình chính và báo cáo đối chứng 2×2. LTR tốt hơn Baseline trong offline synthetic; chưa tốt hơn linear full. Quỹ giảm trong main run; không có kết luận hòa vốn. Cổng xác suất hoàn tất chưa đủ chất lượng nên bị tắt. [Báo cáo nghiên cứu](research.md) nêu số liệu, mẫu số, CI và kết quả không ủng hộ giả thuyết.

## Những phần chưa được xác nhận

1. **S1/người thật:** công cụ và phân tích đã có; chưa có 100–200 người thật, H4 và đánh giá human pending.
2. **Hạ tầng đích:** máy hiện tại không có Docker/PostgreSQL/OSRM. Mã Compose, migration, spatial index và hai profile đã chuẩn bị; chưa chạy cạnh tranh PostgreSQL, hai graph OSM thật hay hiệu chỉnh xe máy V-03. Đa giác vùng hiện là minh họa.
3. **Benchmark đầy đủ:** một main run và các smoke không thay thế 20 seed × 18 ô × 50.000 yêu cầu, đo tải API/worker/RTV và các tình huống lỗi RPC kéo dài.
4. **Blockchain ngoài máy:** hợp đồng và adapter đã chạy EVM localhost; testnet/finality/đối soát nhiều worker chưa thực thi. Được hoãn theo chỉ đạo người dùng.
5. **An toàn vận hành:** KYC/SOS là mô phỏng. Quỹ chưa có bằng chứng bền vững. Khóa lệnh và fail-closed bảo vệ tiền, nhưng không thay thế audit hợp đồng và kiểm định triển khai.
6. **Toolchain:** Hardhat phụ thuộc Zod 3 có advisory mức high ở dev dependency đã ghi trong [escrow.md](escrow.md). Không ép override Zod 4 vì khác API. Pytest còn cảnh báo Starlette về hướng chuyển TestClient sang httpx2; frontend có cảnh báo cấu hình Vitest tương lai. Các cảnh báo không làm kiểm thử thất bại.

Kết luận bàn giao là **nguyên mẫu đầy đủ các lớp triển khai và đã kiểm chứng local trong phạm vi nêu trên**. Chưa đủ bằng chứng để đánh dấu mọi điều kiện nghiệm thu MUST/SHOULD là hoàn tất hoặc tuyên bố “không còn một lỗi”. [Ma trận yêu cầu](requirements.md) là danh sách truy vết để hoàn tất các phần còn thiếu.

## Tự đánh giá theo bằng chứng

| Tiêu chí | Điểm / 5 | Bằng chứng và cải thiện cần thiết |
|---|---:|---|
| Chính xác | 4 | Có test/vector và kết quả âm được giữ; chưa kiểm chứng PostgreSQL/OSRM/testnet |
| Đầy đủ | 3 | Mã đã phủ các năng lực trong scope; human data và main benchmark đầy đủ còn thiếu |
| Rõ ràng | 4 | Có README, phân tích, ma trận và artifact; tài liệu gốc lớn cần dùng chỉ mục khi rà soát |
| Có thể thực hiện | 4 | Có lệnh local/migration/research; cần thêm runtime hạ tầng và dữ liệu thật cho nghiệm thu đích |
| Gọn, tập trung | 4 | Báo cáo chia theo bằng chứng; giữ chi tiết kỹ thuật ở tài liệu chuyên đề |

Trung bình 3,8/5. Ba việc tác động lớn nhất: thực thi bộ test trên PostgreSQL+OSRM; hoàn tất khảo sát thật; chạy ma trận benchmark với model hiện tại. Đây là giới hạn cụ thể của bằng chứng hiện có, không phải điểm số bảo đảm chất lượng vận hành.
