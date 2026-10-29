# Sửa tìm địa chỉ, ghim và tổng quãng đường — 28/10/2026

Bản trực tiếp kiểm thử: **http://127.0.0.1:3020**. Tải lại bằng Ctrl+F5.

## Kết quả chức năng

- Nhập `Jacal Hotel`, `Jacayl Hotel Hà Đông` hoặc `138 Phùng Hưng Hà Nội` trả về cùng địa chỉ **Jacayl Hotel – Hà Đông, 138 Phùng Hưng, Phúc La, Hà Nội**. Danh mục bổ sung có alias, tọa độ và nguồn công khai trong `config/local_places.json`; không cần gọi Photon cho địa điểm đã có trong danh mục.
- Loại kết quả fuzzy khác số nhà hoặc khác đường khi tìm địa chỉ có số nhà; không thay một khách sạn không tìm thấy bằng khách sạn khác chỉ vì cùng từ “Hotel”. Không nhầm số hiệu đường với số nhà. Tìm ngoài danh mục vẫn dùng Photon; dữ liệu công khai không bao phủ mọi số nhà/địa điểm ở Việt Nam.
- Chọn hai điểm sẽ tính tổng km và thời gian theo mạng đường **ô tô**, vẽ tuyến GeoJSON thực. Không dùng khoảng cách đường chim bay nhân hệ số làm quãng đường thực.
- Xóa số km và tuyến cũ khi đang nhập địa chỉ mới; cập nhật khi chọn kết quả, đổi chiều, chạm bản đồ hoặc kéo ghim. Bỏ qua phản hồi của hành trình đã đổi. Không có tuyến khi dịch vụ lỗi: thông báo lỗi và cho phép thử lại.
- Ghim SVG có đầu nhọn trùng điểm tọa độ; chữ A/B thẳng, kéo A luôn sửa điểm đón và kéo B luôn sửa điểm đến. Giữ tọa độ người dùng chọn, nối nét đứt tới điểm đường mà router sử dụng. Cảnh báo nếu ghim cách đường ô tô hơn 50 m; không nhận tuyến nếu điểm đường cách ghim hơn 1 km. GPS yêu cầu vị trí mới và độ chính xác cao từ trình duyệt.

## Độ chính xác và phạm vi cần phân biệt

Nguồn [Trip.com của địa chỉ 138 Phùng Hưng](https://vn.trip.com/hotels/hanoi-hotel-detail-114281361/jacayl-hotel/) cung cấp điểm `20.968238, 105.786924`. Một listing khác cùng tên cung cấp điểm cách đó hơn 1 km. Chưa có khảo sát cổng thực tế hoặc ghim được chủ địa điểm/người dùng xác nhận. Vì vậy kết quả bổ sung được ghi rõ **vị trí tham khảo, chưa xác minh cổng đón**, có link nguồn và cho phép chỉnh ghim. Không tuyên bố đây là tọa độ cổng chính xác. Địa chỉ thủ công luôn cần người dùng xác nhận ghim.

Tuyến ô tô có thể khác tuyến xe máy và không chứa giao thông trực tiếp. Km là độ dài tuyến giữa hai điểm đường, không gồm đoạn từ ghim tới đường; giao diện có đường nối và cảnh báo khoảng cách đó. Giá/gợi ý chuyến của môi trường `fixture` tiếp tục dùng dữ liệu kiểm thử riêng, có thông báo trên giao diện. Bộ giá baseline được giữ nguyên; chưa nghiệm thu tích hợp định tuyến thật vào toàn bộ ghép chuyến, giá và hành trình xe máy.

## Dịch vụ và API

`POST /api/locations/route` nhận đúng hai tọa độ `pickup`, `dropoff`, yêu cầu phiên đăng nhập; xác thực kết thúc transaction trước khi gọi HTTP ngoài. URL chỉ lấy từ cấu hình operator `RISE_ROUTE_PREVIEW_URL` (mặc định FOSSGIS routed-car); người dùng không được truyền URL hoặc redirect. Chỉ tọa độ gửi cho router, không chuyển cookie hay dữ liệu hành khách.

Tuân theo [điều kiện FOSSGIS](https://routing.openstreetmap.de/about.html): cache 15 phút, LRU 256 tuyến, tối đa một truy vấn ngoài đang chạy/mỗi tiến trình và cách nhau ít nhất 1,1 giây; dùng Redis cho cache và khoảng cách truy vấn giữa các tiến trình khi cấu hình. Thêm giới hạn 30 yêu cầu/người/phút, timeout 12 giây, User-Agent định danh và attribution/link báo lỗi. Đây là dịch vụ công cộng cho lưu lượng nghiên cứu nhỏ, không có SLA. Vận hành nhiều người cần router riêng hoặc nhà cung cấp phù hợp.

Theo [API OSRM](https://project-osrm.org/docs/v5.24.0/api/), request/GeoJSON dùng `[kinh độ, vĩ độ]`, Leaflet dùng `[vĩ độ, kinh độ]`; backend trả mét/giây, UI đổi sang km/phút. Kiểm tra tính hữu hạn, giới hạn tọa độ, hình học và khoảng cách snap trước khi trả thành công.

## Bằng chứng kiểm thử

- Backend toàn bộ: 116/116 đạt trước khi thêm hai regression cho đường có số hiệu và số nhà trong ngõ; bộ geocoding + route cuối cùng 32/32 đạt, bao gồm hai regression đó.
- Frontend unit: 19/19; browser: 18/18, có chọn địa chỉ, đổi chiều, kéo đúng ghim khi focus điểm khác, tip ghim trùng tọa độ, lỗi dịch vụ, tự chờ giới hạn truy vấn. TypeScript, Ruff và production build đạt.
- Thử thật UI → API → Photon/FOSSGIS, không mock: `144 Xuân Thủy` → địa điểm bổ sung trên trả **10.566,1 m**, **797,2 giây**, 228 điểm hình học; giao diện hiển thị **10,57 km**, khoảng **14 phút**. Kết quả phụ thuộc tọa độ tham khảo đã nói rõ ở trên.
- Đầu nhọn hai ghim khớp tọa độ vẽ tại thời điểm đo, sai lệch **0 px/0 px**; đây là kiểm tra phép chiếu/anchor trên giao diện, không phải chứng nhận vị trí địa lý thực tế.
- Ba cách tìm trên đều đạt; màn hình 375 px không tràn ngang; không có JavaScript runtime error; không tạo trip request, booking hay giao dịch tiền trong lần thử này.

Xem bằng chứng cuối trên bản đang chạy: [JSON](../artifacts/maps/route-live-v4/results.json), [máy tính](../artifacts/maps/route-live-v4/desktop.png), [điện thoại](../artifacts/maps/route-live-v4/mobile.png), [SHA-256 mã nguồn và đối chiếu bản build](../artifacts/maps/route-live-v4/source-fingerprint.json). Script tái lập: `web/tests/route-live.cjs`; đặt `ROUTE_TEST_OUTPUT` sang thư mục phiên bản mới để không ghi đè bằng chứng.
