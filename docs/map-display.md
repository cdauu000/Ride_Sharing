# Bản đồ trong bản chạy local

Bản đồ ở mục **Tìm chuyến** hiển thị đường phố, nhãn địa danh và hai điểm A/B. Có thể kéo, phóng to/thu nhỏ, bấm để chọn điểm đón hoặc điểm đến và đưa bản đồ về toàn bộ hành trình.

Nguồn mặc định của bản nghiên cứu local là `https://tile.openstreetmap.de/{z}/{x}/{y}.png` do FOSSGIS cung cấp, có ghi nguồn OpenStreetMap/FOSSGIS trực tiếp trên bản đồ. Nguồn OpenStreetMap chuẩn là phương án thứ hai trong ô **Nền bản đồ**. Khi toàn bộ lớp nền không tải được, ứng dụng thử nguồn còn lại một lần; lỗi riêng một ô ảnh không làm biến mất các ô đã tải. Nút **Tải lại bản đồ** thử lại sau khi có kết nối, giữ nguyên điểm A/B.

Ngày 28/10/2026, tên miền `tile.openstreetmap.org` trên máy hiện tại được DNS trả về loopback `127.0.0.1`/`::1`, kết nối HTTPS bị từ chối. Nguồn `tile.openstreetmap.de` tải được qua kết nối thật. Không chỉnh file hosts, DNS hệ thống hoặc bỏ kiểm tra chứng chỉ để xử lý vấn đề này.

Đổi mặc định bằng biến môi trường frontend `NEXT_PUBLIC_MAP_PROVIDER=osm` hoặc `osm-de` **trước khi build**. Chỉ có hai nguồn HTTPS đã định nghĩa trong mã; không nhận URL proxy tùy ý từ người dùng và không chuyển cookie phiên của ứng dụng cho nhà cung cấp bản đồ. Tile dùng cache trình duyệt bình thường, không tải trước toàn vùng hay đóng gói bản đồ offline.

Nguồn này phù hợp lượt kiểm thử nghiên cứu local hiện tại; trước vận hành thương mại cần cấu hình nguồn tile đáp ứng lưu lượng và điều kiện sử dụng tương ứng. Xem [điều kiện FOSSGIS](https://www.openstreetmap.de/germanstyle/) và [chính sách OpenStreetMap chuẩn](https://operations.osmfoundation.org/policies/tiles/). CARTO hiện yêu cầu khóa cho raster tile; dự án không dùng một khóa giả hoặc ẩn watermark để thay thế.

Ngày 28/10/2026 đã bổ sung tuyến ô tô thực và tổng km qua OSRM/FOSSGIS. Đường liền là tuyến đường bộ, nét đứt chỉ nối ghim tới đường. Giá và ghép chuyến ở chế độ fixture vẫn dùng dữ liệu kiểm thử riêng. Xem [báo cáo cập nhật, nguồn vị trí và giới hạn](route-preview-fix-2026-10-28.md).

## Kiểm tra sau sửa

Build production, TypeScript, Prettier và 15 unit frontend đạt. **11/11 browser regression đạt**, gồm lỗi một ô ảnh, chuyển nguồn khi toàn bộ nguồn lỗi, phục hồi bằng nút tải lại, chọn tọa độ trên bản đồ và đổi điểm đến nhiều lần sau khi chuyển nguồn. Đã sửa thứ tự gỡ sự kiện Leaflet để lớp cũ không còn nhận sự kiện khi đã bị tháo.

Kiểm tra kết nối thật không mock tải đủ **12/12 ô ảnh** trong khung máy tính, có hai điểm A/B; kiểm thêm khung 375 px và nút xem toàn bộ hành trình. Không ghi nhận lỗi JavaScript hoặc API 5xx trong lượt này. Axe không ghi nhận vi phạm tự động trong vùng bản đồ điện thoại; các mục cần kiểm tra thủ công được giữ nguyên, không coi đây là chứng nhận WCAG đầy đủ.

Bằng chứng: [máy tính](../artifacts/maps/map-display-v3/map-live.png), [điện thoại](../artifacts/maps/map-display-v3/map-mobile.png), [kết quả thật](../artifacts/maps/map-display-v3/results.json), [axe](../artifacts/maps/map-display-v3/accessibility.json). Mật khẩu và cookie phiên không được ghi vào kết quả.
