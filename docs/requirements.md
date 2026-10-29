# Ma trận phạm vi và bằng chứng

Trạng thái `LOCAL` nghĩa là có triển khai và bằng chứng local; không đồng nghĩa đã nghiệm thu đầy đủ trên OSRM/PostGIS/testnet. `DATA_PENDING` cần dữ liệu thật hoặc kiểm định thực nghiệm. Phạm vi do người dùng xác nhận là toàn bộ MUST và SHOULD.

Sau sửa lỗi sử dụng, bộ UAT mở rộng đạt 31/31 với API/worker thật; đã kiểm thêm no-show, hủy muộn, sự cố tài xế, từ chối ghép, đủ ghế tự nhiên và chạy dưới ngưỡng. [Báo cáo cập nhật](acceptance-retest-2026-10-28.md) không thay thế các giới hạn dữ liệu/hạ tầng trong bảng này.

| ID | Thực hiện chính | Bằng chứng và giới hạn |
|---|---|---|
| M1 | `domain/trips`, `services/trip`, GeoJSON/PostGIS | LOCAL: luật năm dịch vụ, biên 72h, vùng đệm; đa giác thực tế chưa được phê chuẩn |
| M2 | `routing`, `motorbike.lua`, Compose/preprocess | Adapter/profile có mã; chưa chạy hai graph OSRM ở môi trường này; V-03 pending |
| M3 | `domain/pooling`, candidate, intercity optimizer | LOCAL: capacity, thời gian, detour, ngân sách, xã hội; chưa kiểm định mọi tuyến OSM thật |
| M4 | forward-only insertion, tracking traveled, frozen prices | LOCAL: engine và auto-add workflow; vector khóa giá khách thứ ba có kiểm thử toán |
| M5 | rational pricing, cancellation, fund/payouts | LOCAL: chuẩn A/B, hai ghế, 7.300 guarantee, phí hủy, ledger; thanh khoản dài hạn phải kiểm định |
| M6 | booking/version/idempotency/hold/jobs/outbox | LOCAL: tranh ghế 20 luồng, chuỗi ba offer, same-timestamp ordering; PostgreSQL race chưa thực thi |
| M7 | intercity publish/book/close/merge/topup/T24 | LOCAL: đủ ghế, thiếu ghế, góp thêm/hoàn; cần benchmark lịch lớn |
| M8 | private intercity NOW/SCHEDULED | LOCAL: luật bảy ngày, giá 637.000, lịch cả chiều về |
| M9 | Baseline + diversity Top-K | LOCAL: ba dịch vụ trong cùng menu, giá tối đa dùng lọc ngân sách |
| M10 | `research/simulator`, shared domain engine | LOCAL: SHA tái lập, hành vi phi tuyến, nhãn ghép từ lộ trình thật trong mô phỏng |
| M11 | OOF match/fulfill, calibration, LambdaMART, 2×2, reports | Main dataset 50.000 yêu cầu/28 ngày và model thật; H1 synthetic dương, H2/H9 không được ủng hộ; ma trận main đa seed và human pending |
| M12 | Solidity/ABI/local journal/Web3/HD/HMAC | EVM local và Python adapter đã kiểm thử; testnet hoãn theo chỉ đạo người dùng |
| M13 | Next.js workbench, polling/live tracking | LOCAL: role views, browser tests, backend thật; bản đồ tile ngoài có thể không tải khi mất mạng |
| M14 | pytest/property/concurrency/EVM/browser | Có bộ kiểm thử; không tuyên bố toàn bộ G01–G18 đã được chứng minh trên hạ tầng đích |
| S1 | public survey, anonymous storage/export, GroupKFold/statistics | DATA_PENDING: chưa có 100–200 người thật, chưa kết luận H4 |
| S2 | conditional three-gate fulfill, cross-fitted features | LOCAL pipeline; chất lượng xác suất và H5 cần dữ liệu đủ nhãn |
| S3 | temperature + ECE gates | Chặn phép nhân nếu thiếu cổng; không ép bật khi thiếu bằng chứng |
| S4 | actual RTV CP-SAT and bounded fallback | LOCAL engine/backend; chỉ xử lý HELD chưa ký quỹ, admission theo trần ma trận; benchmark 500 requests pending |
| S5 | merge two-hour protection + unanimous topup | LOCAL; kiểm thử hoàn phần góp khi từ chối xác định, chặn RUN khi RPC còn chưa rõ, retry giữ operation ID |
| S6 | cancellation tiers, arrival evidence, five-minute no-show | LOCAL; không được phạt no-show trước cửa sổ đón; hủy driver không kích hoạt guarantee phá ghép |
| S7 | admin KYC mock + gates | LOCAL: quyền admin, kiểm tra lại KYC ở accept; không phải eKYC thật |
| S8 | admin ledger/metrics/jobs/models/surveys/batch | LOCAL; các số chưa đủ mẫu hiển thị chưa có dữ liệu |
| S9 | privacy/share-token/SOS/same-gender constraints | LOCAL; SOS là mô phỏng, không liên lạc khẩn cấp; giới tính chưa xác thực không được suy đoán |

## Cổng đúng đắn và phạm vi kiểm chứng

| Cổng | Bằng chứng hiện có | Phần phải kiểm định thêm |
|---|---|---|
| G01/G02 | constraint tests, all-rider evaluation, last-seat test | các tuyến thực, đồng thời PostgreSQL |
| G03/G04 | idempotency, stale version, local journal/chain retry | lỗi mạng và tải đa worker ở môi trường đích |
| G05/G06/G07 | 10.000 tổ hợp, bound/cap/rounding, contract checks | kiểm thử toàn hệ trên dữ liệu thật |
| G08 | frozen/dynamic regression, forward-only prefix | kịch bản GPS và hủy phức hợp thực tế |
| G09 | post-rounding gate, canonical hourly vector | benchmark kinh tế nhiều quần thể |
| G10/G13 | service inference/type/capacity checks | đầu vào địa lý OSM đã xác nhận |
| G11 | walking mặc định 0; C9 không thuộc phạm vi | không tuyên bố đã xây meeting points |
| G12 | ledger/payout/guarantee exact-integer tests | đối soát vận hành multi-worker/testnet |
| G14/G15 | 72h close, voluntary topup and merge checks | full matrix intercity lifecycles at scale |
| G16 | same-service cascade and third-offer hold | tải điều phối ngoài fixture |
| G17 | pending deposit start rejected | lỗi RPC/finality dài hạn |
| G18 | integer EVM/local split, replay and atomic failure | testnet receipts/finality/DB reconciliation |

Không dùng một bài test thành công để kết luận cổng có 0 vi phạm với mọi trạng thái có thể. Số liệu và các lần chạy hiện có được ghi ở [báo cáo kiểm chứng](verification.md).
