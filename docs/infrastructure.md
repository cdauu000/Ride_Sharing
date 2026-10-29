# Chạy và kiểm định hạ tầng

## Hai chế độ được phân biệt

Local độc lập dùng SQLite + routing fixture + escrow journal. Hạ tầng đầy đủ dùng PostgreSQL/PostGIS + Redis + OSRM hai profile, có thể nối EVM local hoặc testnet sau này. Không dùng bằng chứng SQLite/fixture để khẳng định benchmark PostgreSQL/OSRM.

Trong môi trường thực hiện hiện tại chưa có Docker/PostgreSQL/PostGIS. Các file Compose, Lua và migration được chuẩn bị; bước thực thi hạ tầng này vẫn phải được kiểm chứng khi có runtime phù hợp. Không có lệnh cài Docker hay thay cấu hình hệ điều hành được thực thi tự động.

## PostgreSQL/PostGIS và Redis

1. Tạo `.env` từ mẫu hoặc bằng `python -m app.cli init-demo`. Đặt `POSTGRES_PASSWORD` bằng giá trị riêng không có ký tự cần escape trong URL, hoặc tự cấu hình một `RISE_DATABASE_URL` đã URL-encode.
2. Chạy `docker compose up -d postgres redis`.
3. Trỏ `RISE_DATABASE_URL` tới database **mới**; đặt `RISE_AUTO_CREATE_SCHEMA=false`.
4. Chạy `.venv\Scripts\python.exe -m alembic upgrade head`.
5. Backend nạp các vùng GeoJSON vào PostGIS khi khởi động. Bản vùng đang kèm theo là `ILLUSTRATIVE_REQUIRES_VALIDATION`; cần thay bằng vùng đã kiểm định và lưu mã băm.

Migration tạo CHECK/UNIQUE/partial indexes, geometry được sinh từ vị trí tài xế, GIST geometry/geography, bảng vùng phục vụ, index quét job/chuyến và trigger cấm sửa snapshot/config/sổ cái. Tài khoản DB khởi tạo cần quyền tạo extension PostGIS; tài khoản runtime nên được giảm quyền sau migration.

SQLite demo dùng `create_all`; không tự gán một migration version cho schema có sẵn. Muốn chuyển dữ liệu demo sang Postgres cần đối chiếu schema và chuyển dữ liệu riêng, không chạy reset/xóa database.

## Dữ liệu và hai graph OSRM

```powershell
.venv\Scripts\python.exe scripts/prepare_osrm.py
# Hoặc dùng PBF đã có:
.venv\Scripts\python.exe scripts/prepare_osrm.py --pbf C:\path\to\northern-vietnam.osm.pbf
docker compose --profile routing up -d osrm-car osrm-motorbike
```

Script lấy bản trích công khai từ [Geofabrik](https://download.geofabrik.de/asia/vietnam.html), ghi SHA-256 và xây riêng car/motorbike bằng extract → partition → customize theo [hướng dẫn OSRM](https://github.com/Project-OSRM/osrm-backend). Việc preprocess cần dung lượng và thời gian đáng kể; manifest không được ghi thành công nếu một bước thất bại. Profile motorbike chặn motorway/motorway_link và motorroad, đổi access hierarchy sang motorcycle. Hệ số tốc độ hiện là giá trị xuất phát cần kiểm định V-03.

Đặt `RISE_ROUTING_MODE=osrm`, hai URL cổng 5000/5001 và Redis. API không âm thầm đổi sang đường chim bay khi OSRM lỗi; trả `ROUTING_UNAVAILABLE` hoặc `NO_ROUTE`. Chỉ cache ma trận đúng profile và tọa độ.

Một đợt gợi ý gom tọa độ và dùng một ma trận mỗi profile. Số kế hoạch/chuyến được xét bị chặn để nằm trong trần 200 điểm của OSRM table. Batch admission cũng chặn tổng điểm; phần chưa nhận vào vòng này phải được ghi trong báo cáo backlog. Cần benchmark sự đánh đổi coverage/latency của trần này.

## Ứng dụng bằng Compose

`docker compose --profile application up --build` chạy migration trước API/worker rồi frontend. Profile `routing` chỉ bật khi graph đã được tạo. Nếu dùng Web3 RPC chạy trên máy host, URL bên trong container phải trỏ đúng host; `127.0.0.1` trong container không phải máy host.

Compose không chứa mnemonic/khóa ký cố định. Chưa bật chế độ ngoài development cho đến khi secrets, cookie HTTPS, PostgreSQL migrations, OSRM, vùng phục vụ và Web3 đã được cấu hình. Những guard này kiểm tra cấu hình; không thay kiểm thử vận hành.

Image backend chứa ABI trong `contracts/abi`, không chứa Hardhat hay khóa ký. Model được mount read-only từ `artifacts/models`; đặt `RISE_MODEL_ARTIFACT_PATH` tới đường dẫn trong container nếu muốn bật model. Frontend dùng URL API trong mạng Compose ở thời điểm build; thay đích API cần build lại. Các cấu hình container này chưa được chạy Docker trong môi trường hiện tại.

## Kiểm định cần chạy trên hạ tầng đích

- 20 client tranh ghế cuối trên PostgreSQL, gồm race với T−72h; kiểm tra deadlock/retry và không mất update.
- Hai worker nhận job song song; kill/restart giữa broadcast và áp receipt; đối soát từng operation.
- Các tuyến xe máy cố tình có lựa chọn cao tốc: không được sinh route xe máy vào motorway.
- 20 cặp điểm kiểm định tốc độ motorbike; lưu khoảng cách/thời gian và phiên bản PBF/profile.
- p95 sinh ứng viên/gợi ý, mô hình và worker theo Mục 77. Report phải ghi số tài xế, yêu cầu, cấu hình máy, cache hit và phiên bản dữ liệu.
- Token liability + số dư Quỹ on-chain phải khớp với trạng thái DB sau khi outbox không còn lệnh chưa xác nhận.
