# Hướng dẫn kiểm thử trực tiếp bản đã sửa

Cập nhật 28/10: có tổng km và tuyến ô tô thực khi chọn hai điểm; tìm được Jacal/Jacayl Hotel tại 138 Phùng Hưng qua danh mục bổ sung, có nhãn vị trí tham khảo và kéo ghim. Xem [báo cáo bản đồ, nguồn vị trí và giới hạn](route-preview-fix-2026-10-28.md).

Mở **http://127.0.0.1:3020**. Đây là bản production local dùng database riêng tại `artifacts/review/rise.db`, khác dữ liệu chạy nghiệm thu và database `rise.db` cũ. Thời gian của bản review bắt đầu bằng đồng hồ thực; chưa tiến nhanh thời gian. Tiền và tính giá/ghép chuyến dùng dữ liệu kiểm thử; phần xem trước bản đồ dùng tuyến ô tô thật, được phân biệt trên giao diện.

Trong **Tìm chuyến**, nền bản đồ đường phố có chọn nguồn và nút tải lại khi lỗi. [Chi tiết bản đồ](map-display.md).

Hai ô điểm đón/đến hỗ trợ **nhập địa chỉ cụ thể**: nhập số nhà/tên đường/khu vực → bấm kính lúp hoặc Enter → chọn kết quả → kiểm tra ghim. Địa chỉ chưa có dữ liệu có thể nhập thủ công và xác nhận tại ghim đã chọn. [Hướng dẫn địa chỉ](address-search.md).

## Đăng nhập và chuẩn bị

Mở cửa sổ trình duyệt thường cho hành khách và cửa sổ ẩn danh cho tài xế. Hai tab trong cùng một cửa sổ dùng chung phiên đăng nhập.

| Vai trò | Email | Dùng để kiểm tra |
|---|---|---|
| Khách thứ nhất | `passenger@rise.local` | Tìm, đặt, hủy, theo dõi, đánh giá |
| Khách thứ hai | `passenger2@rise.local` | Ghép một booking độc lập |
| Tài xế xe máy | `bike@rise.local` | Nhận xe máy, đón/trả khách |
| Tài xế ô tô | `driver@rise.local` | Bao xe, Pool, đăng ghép liên tỉnh |
| Tài xế phụ | `driver2@rise.local`, `driver3@rise.local` | Thử chuỗi chuyển offer |
| Quản trị | `admin@rise.local` | KYC, Quỹ, job, đồng hồ demo |

Mật khẩu chung là giá trị **`RISE_DEMO_PASSWORD` trong `.env`** ở thư mục dự án. Mật khẩu này không được ghi vào báo cáo hoặc gói bàn giao.

Ở database review mới, chỉ `bike` và `driver` trực tuyến sẵn; tài xế phụ tắt nhận chuyến để bạn dễ kiểm tra. Tài xế vào **Dành cho tài xế → Cấu hình**, cập nhật vị trí `20.961, 105.747` trước khi đặt nếu vị trí đã cũ. Mở sẵn màn hình tài xế: offer nội đô chỉ có **20 giây** để phản hồi.

## Các luồng nên thử

1. **Bao xe nội đô:** khách chọn Phenikaa → Đống Đa, 1 người, ngân sách tối đa 800.000. Kiểm tra giá 194.000; chọn chuyến. Tài xế xem điểm đón/trả, thu nhập 155.200 và ước tính theo giờ trước khi nhận. Sau khi ký quỹ xác nhận, bắt đầu chuyến, xác nhận lần lượt điểm đón/trả rồi hoàn thành. Khách kiểm tra bảng tiền và đánh giá.
2. **Xe máy:** lặp lại với `bike`; cước 81.000, tài xế 64.800. Thử tìm cho 2 người hoặc có hành lý lớn: xe máy phải bị loại.
3. **Pool thực sự:** khách thứ nhất đặt Phenikaa → Đống Đa và tài xế nhận. Trước khi khởi hành, khách thứ hai dùng một phiên đăng nhập khác đặt La Phù → Nguyễn Trãi. Hai booking phải cùng kế hoạch. Hoàn tất theo thứ tự điểm dừng; giá cuối chuẩn 143.000 và 105.000, tổng tài xế 210.800. Hai ghế trong **cùng booking** không được tính là ghép hai khách độc lập.
4. **Hủy và sự cố:** hủy trước nhận chuyến phải có phí 0, trạng thái “Chưa ký quỹ”. Hủy bao xe nội đô sau nhận quá 120 giây có phí trần 20.000. Tài xế báo sự cố trước đón phải hoàn đủ tiền khách. Báo khách không đến chỉ mở sau khi xác nhận đến điểm đón và đủ thời gian chờ hợp lệ.
5. **Liên tỉnh:** tài xế đăng Hà Đông → Hưng Yên sau 4 ngày; khách chọn Hẹn trước, cùng giờ đi. Giá tham chiếu 200.000/ghế, ngưỡng mặc định 3 ghế. Dùng Admin tiến đồng hồ và chạy job đến hạn để xem đóng đặt T−72h, góp thêm tự nguyện hoặc quyết định chạy dưới ngưỡng, chốt thứ tự T−24h. Nút bắt đầu chỉ mở khi đến giờ khởi hành và ký quỹ đủ. Trường hợp 2 ghế góp thêm: tổng 636.000, tài xế 540.600. Đủ 3 ghế tự nhiên: tổng 600.000, tài xế 540.000.
6. **Lỗi tìm kiếm và màn hình nhỏ:** có menu rồi đổi điểm đến; thẻ cũ phải biến mất ngay. Thử 375 px, nút điều hướng và bảng thu nhập vẫn dùng được. Khi nền bản đồ không tải, vẫn có danh sách địa điểm và ô tọa độ.

Không tiến đồng hồ khi còn một chuyến nội đô cần giữ: thao tác này cũng làm các offer và hạn chờ của chuyến đó hết hiệu lực. Có thể tải lại trang sau khi tiến thời gian để thấy dữ liệu mới ngay.

## Khởi động lại khi cần

Từ `C:\Rise_Sharing`, mở hai terminal:

```powershell
# Terminal 1 — API, worker, dữ liệu review:
cmd /c scripts\run-review-api.cmd

# Terminal 2 — giao diện production đã build:
cmd /c scripts\run-review-web.cmd
```

Đóng bằng Ctrl+C trong từng terminal. Không cần chạy lại nếu địa chỉ 3020 đang hoạt động. Để build lại sau khi sửa mã, dừng giao diện rồi chạy `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\prepare-review.ps1`, sau đó chạy lại terminal 2. Các lệnh không xóa dữ liệu review hoặc ghi đè dữ liệu demo cũ.

Khi báo lỗi, ghi vai trò, mã booking/chuyến, các bước đã làm, kết quả mong đợi và kết quả thực tế. Không đưa mật khẩu hoặc khóa bí mật vào ảnh chụp.

## Giới hạn của bản trực tiếp kiểm thử

Đây là bản kiểm chứng chức năng tại máy hiện tại. Xem trước tuyến ô tô qua dịch vụ OSRM/FOSSGIS công cộng đã được kiểm thử kết nối thật. PostgreSQL/PostGIS, OSRM tự vận hành và đồng bộ định tuyến thật vào tính giá/ghép chuyến, GPS/chuyến xe thực địa, thiết bị iOS/Android thật, khảo sát người thật và triển khai testnet chưa được nghiệm thu. Testnet được hoãn theo yêu cầu của bạn. Những phần cần dữ liệu thực không được thay bằng dữ liệu giả để tuyên bố đạt.
