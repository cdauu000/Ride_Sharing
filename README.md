# Rise Sharing / Chung Đường — Revision 9

Nguyên mẫu nghiên cứu đặt xe năm dịch vụ theo bốn tài liệu gốc trong workspace. Phạm vi đã xác nhận: **M1–M14 và S1–S9**; **chưa deploy ra mạng bên ngoài**.

Backend FastAPI, giao diện Next.js, định giá xác định bằng số hữu tỷ, mô phỏng/LightGBM, ký quỹ Solidity và bộ kiểm thử nằm trong cùng dự án. Cấu hình đã phê duyệt được trích nguyên từ baseline, không thay các tỷ lệ giá để làm đẹp kết quả.

**Bản để trực tiếp test sau sửa lỗi:** http://127.0.0.1:3020 — [hướng dẫn vai trò, tài khoản và thao tác](docs/direct-testing.md). Dữ liệu review riêng, không dùng lại dữ liệu nghiệm thu. Lượt kiểm thử lại đạt **31/31 kịch bản UI với backend thật**; xem [báo cáo sau sửa](docs/acceptance-retest-2026-10-28.md).

Điểm đón/đến đã có [nhập và tìm địa chỉ cụ thể](docs/address-search.md), chọn kết quả trên bản đồ và xác nhận địa chỉ tự nhập tại ghim; danh sách địa điểm mẫu nằm trong phần mở rộng.

**Trạng thái nghiệm thu:** có bản chạy local và bằng chứng kiểm thử; chưa thể tuyên bố toàn bộ Definition of Done đạt. Dữ liệu khảo sát người thật, thực thi PostgreSQL/PostGIS + OSRM trong môi trường đích, hiệu chỉnh xe máy và deploy testnet vẫn cần xác nhận. Xem [báo cáo kiểm chứng](docs/verification.md), [ma trận truy vết](docs/requirements.md) và [phân tích hệ thống](docs/system-analysis.md).

[Gói bàn giao và cách kiểm tra](docs/delivery.md) mô tả archive mã nguồn, model và dữ liệu đi kèm; bí mật và database demo được loại khỏi gói.

## Chạy local trên Windows

Yêu cầu Python 3.12+, Node.js 24 LTS. `.venv` đã được tạo trong workspace hiện tại.

`requirements-lock.txt` ghi phiên bản Python đã dùng để kiểm chứng. Khi cần tái tạo đúng môi trường, cài file lock trước rồi cài dự án với `pip install --no-deps -e .`; thực hiện từ thư mục gốc để sử dụng cấu hình, ABI và artifact đi kèm.

```powershell
# Khi tạo môi trường mới:
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,research]"
npm.cmd --prefix web ci
npm.cmd --prefix contracts ci

# Chuẩn bị tài khoản và bí mật thử nghiệm, không ghi đè .env đã có:
.venv\Scripts\python.exe -m app.cli init-demo

# Terminal 1:
cmd /c scripts\run-local.cmd

# Terminal 2:
cmd /c scripts\run-web.cmd
```

Mở **http://127.0.0.1:3000**. API local: **http://127.0.0.1:8010/docs**. Cổng 8010 được dùng để tránh dịch vụ đang chiếm cổng 8000 trên máy hiện tại. Có thể đổi cổng Uvicorn và đặt `API_BASE_URL` tương ứng trước khi chạy Next.js.

Tài khoản demo: `passenger@rise.local`, `passenger2@rise.local`, `bike@rise.local`, `driver@rise.local`, `driver2@rise.local`, `driver3@rise.local`, `admin@rise.local`. Mật khẩu chung **được sinh ngẫu nhiên**, lưu ở `RISE_DEMO_PASSWORD` trong `.env`; không có mật khẩu quản trị cố định trong mã nguồn.

Chế độ mặc định dùng **routing fixture minh họa** và **ký quỹ tài chính local**, hiển thị rõ trên giao diện. `tx_hash = null` trong chế độ local; không giả mạo giao dịch blockchain. Các token Solidity là tín dụng nghiên cứu, không dùng tiền thật.

## Các luồng có thể chạy

1. Hành khách tìm chuyến Phenikaa → Đống Đa: xe máy 81.000 VND, bao xe 194.000 VND, Pool dự kiến 145.000 VND, trần ghép 155.000 VND, trần không ghép 174.000 VND trong fixture chuẩn.
2. Chọn chuyến; đăng nhập tài xế đúng xe để nhận offer. Worker ký quỹ bất đồng bộ. Khởi hành bị chặn nếu chưa có tiền ký quỹ xác nhận.
3. Tài xế bắt đầu, xác nhận lần lượt các điểm đón/trả, rồi đóng chuyến. Theo dõi ba trục trạng thái và bảng tách tiền thu/thu nhập/Quỹ.
4. Pool hai booking độc lập: tạo thêm La Phù → Nguyễn Trãi trước khi đóng cửa ghép; backend tự kiểm tra chèn, giá khách cũ và sức chứa. Hai người trong một booking không được coi là ghép thành công.
5. Liên tỉnh: tài xế đăng chuyến Hà Đông → Hưng Yên trước 3–7 ngày; hành khách đặt ghế; worker xử lý T−72h, gộp/góp thêm, quyết định T−60h và tối ưu thứ tự T−24h. Admin có đồng hồ demo **chỉ cho local** để không phải chờ nhiều ngày.
6. Khảo sát ẩn danh tại `/survey`; dữ liệu thật phải được thu hợp lệ trước khi kết luận H4 và đánh giá trên người thật.

Xem [kịch bản nghiệm thu](docs/acceptance.md) để biết điều kiện và giá trị mong đợi.

## Kiểm thử

```powershell
.venv\Scripts\python.exe -m ruff check app research tests scripts migrations
.venv\Scripts\python.exe -m pytest --junitxml=artifacts/test-results.xml
npm.cmd --prefix web run typecheck
npm.cmd --prefix web test
npm.cmd --prefix web run test:e2e
npm.cmd --prefix web run build
npm.cmd --prefix contracts test
```

`tests/live-integration.cjs` trong `web` dùng backend thật đang chạy, đọc mật khẩu từ `.env` và chụp màn hình vào `artifacts/screenshots/`. Các browser test mặc định dùng API mock để kiểm tra tương tác UI, được phân biệt với kiểm thử backend thật.

Các ca quan trọng bao gồm 10.000 mẫu phân bổ ngẫu nhiên, vector giá chuẩn, cổng ký quỹ, 20 lượt tranh ghế cuối, chuỗi ba offer, hủy/hoàn tiền, góp thêm và kiểm tra rò rỉ đặc trưng. Chạy được các ca này không phải chứng minh hệ thống không còn lỗi ở mọi đầu vào.

## Nghiên cứu tái lập

```powershell
.venv\Scripts\python.exe -m research simulate --seed 1000 --requests 1000 --days 7 --density HIGH --output artifacts/research/example_v1
.venv\Scripts\python.exe -m research train --dataset artifacts/research/example_v1/observations.jsonl --version example_v1 --output artifacts/models/example_v1
.venv\Scripts\python.exe -m research closed-loop --model artifacts/models/example_v1 --requests 100 --days 7 --seeds 1000:1019 --output artifacts/research/closed_loop_example.json
```

Mỗi đường dẫn phiên bản là bất biến; hãy dùng tên mới khi thay dữ liệu/cấu hình/mã. Simulator gọi engine chèn và định giá thật; không tung đồng xu để gán nhãn MATCHED. Biến sở thích ẩn không được xuất vào tập huấn luyện. Các báo cáo giữ cả kết quả không ủng hộ giả thuyết.

Để bật AI online, đặt `RISE_MODEL_ARTIFACT_PATH` tới thư mục artifact do operator kiểm soát rồi khởi động lại backend. Không nạp file `joblib` từ người dùng không tin cậy. Nếu chưa có artifact, API dùng Baseline có giải thích.

Đã chạy dataset 50.000 yêu cầu và model `artifacts/models/main_v1`. [Báo cáo nghiên cứu](docs/research.md) phân tích H1/H2/H3/H9, Quỹ và giới hạn mẫu; [hướng dẫn khảo sát](docs/survey.md) mô tả S1. Các kết quả không ủng hộ giả thuyết được giữ nguyên.

## PostgreSQL, OSRM và blockchain

- [Hướng dẫn hạ tầng](docs/infrastructure.md): Docker Compose, migration, hai graph OSRM và kiểm định dữ liệu vùng.
- [Hợp đồng và adapter ký quỹ](docs/escrow.md): ABI thật, HD wallet, journal chống chi trùng, lệnh chạy EVM local, các phần cần cấu hình trước testnet.
- `.env.example` mô tả biến môi trường; không đưa `.env`, mnemonic hay khóa riêng vào kho mã.
- Không chạy `alembic upgrade` trực tiếp lên database demo được tạo bằng `create_all` khi chưa đối chiếu/stamp schema; dùng database mới cho kiểm tra migration.

## Cấu trúc

```text
app/domain/        Luật thuần: giá, ràng buộc, chèn động, Baseline, CP-SAT RTV
app/services/      Dịch vụ giao dịch: booking, pooling, intercity, ride, fund
app/http/          Router theo năng lực; kiểm tra đầu vào, vai trò và sở hữu
app/escrow/        Adapter local/EVM, receipt journal, HD wallet, HMAC
research/          Simulator, firewall dữ liệu, OOF, LTR, hiệu chỉnh, thống kê, khảo sát
web/               Next.js workbench cho Khách/Tài xế/Admin
contracts/         Solidity, ABI, kiểm thử EVM và công cụ operator
migrations/        Lịch sử Alembic và PostGIS/index/trigger bất biến
config/            Baseline đã khóa, vùng minh họa, profile motorbike
tests/             Kiểm thử đơn vị, thuộc tính, luồng tích hợp và đồng thời
docs/              Phân tích, phạm vi, bằng chứng và phần còn thiếu
```
