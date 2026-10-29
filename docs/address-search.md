# Nhập địa chỉ cụ thể cho điểm đón và điểm đến

Cập nhật 28/10: đã thêm alias cho Jacal/Jacayl Hotel tại 138 Phùng Hưng, lọc kết quả khác số nhà, kéo ghim và tổng quãng đường ô tô. Xem [báo cáo sửa lỗi và giới hạn tọa độ](route-preview-fix-2026-10-28.md).

Trong **Tìm chuyến**, hai ô **Điểm đón** và **Điểm đến** là ô nhập văn bản. Người dùng có thể nhập số nhà, tên đường, phường/xã và tỉnh/thành; không bị giới hạn trong danh sách địa điểm mẫu.

## Cách dùng

1. Nhập địa chỉ, ví dụ `144 Xuân Thủy, Hà Nội`.
2. Bấm biểu tượng kính lúp hoặc Enter để tìm. Hệ thống chỉ gửi yêu cầu khi người dùng thực hiện thao tác này.
3. Chọn kết quả đúng; có thể dùng mũi tên và Enter. Ghim tương ứng và tọa độ được cập nhật theo kết quả đã chọn.
4. Kiểm tra A/B trên bản đồ rồi bấm **Tìm chuyến phù hợp**.

Nếu số nhà chưa có trong dữ liệu tìm kiếm: chọn ghim chính xác trên bản đồ trước, nhập địa chỉ, bấm **Gắn địa chỉ đã nhập với ghim hiện tại**, kiểm tra nội dung rồi **Xác nhận địa chỉ tại ghim này**. Thao tác này giữ địa chỉ do người dùng nhập và vị trí do họ xác nhận; không giả thành kết quả tra cứu của nhà cung cấp.

Địa điểm mẫu và nhập tọa độ vẫn có trong phần mở rộng để tái lập các kịch bản baseline. Đổi ghim, đổi địa chỉ hoặc đổi chiều hành trình sẽ xóa gợi ý chuyến cũ. Khi đang nhập một địa chỉ mới mà chưa chọn kết quả/xác nhận ghim, hệ thống chặn tìm chuyến để tránh dùng tọa độ trước đó.

## Nguồn dữ liệu và phạm vi

Mặc định dùng dịch vụ Photon với dữ liệu OpenStreetMap, giới hạn kết quả ở Việt Nam. Chỉ địa chỉ người dùng bấm tìm được gửi tới dịch vụ; cookie đăng nhập, mật khẩu, booking và thông tin tài khoản không được chuyển đi. Khi xác nhận địa chỉ thủ công tại ghim, không có yêu cầu tra cứu bên ngoài.

Không phải mọi số nhà/ngõ đều có trong dữ liệu. Kết quả có số nhà được phân biệt với kết quả địa danh/tuyến đường; người dùng vẫn kiểm tra ghim trước khi đặt. Tìm ra địa chỉ không có nghĩa mọi vị trí đều nằm trong vùng phục vụ; các ràng buộc vùng và định tuyến của dự án vẫn được kiểm tra riêng.

[Tài liệu API Photon](https://github.com/komoot/photon/blob/master/docs/api-v1.md) mô tả tìm theo tên/địa chỉ, lọc quốc gia và tọa độ. [Điều kiện máy chủ demo](https://github.com/komoot/photon#demo-server) cho phép lưu lượng vừa phải, không cam kết độ sẵn sàng; trước vận hành nhiều người cần cấu hình dịch vụ riêng hoặc nhà cung cấp phù hợp.

## Cấu hình và kiểm soát

Biến backend `RISE_GEOCODING_SEARCH_URL` mặc định là `https://photon.komoot.io/api/`. Operator có thể đổi sang dịch vụ tương thích Photon mà không sửa frontend. API người dùng không nhận URL upstream tùy ý.

`POST /api/locations/search` yêu cầu phiên đăng nhập hợp lệ; query 3–250 ký tự. Địa chỉ không được đưa vào query string của API trình duyệt. Backend kết thúc transaction xác thực trước khi chờ HTTP bên ngoài để không giữ khóa database khi dịch vụ chậm.

Giới hạn: 20 yêu cầu/người/phút, tối đa một yêu cầu upstream đang xử lý ở mỗi tiến trình và khoảng cách 1,1 giây giữa các lượt mới. Cache kết quả 1 giờ, tối đa 256 query trong bộ nhớ. Nếu có Redis, cache và cổng tốc độ dùng Redis chung; kiểm thử hạ tầng Redis thật vẫn thuộc bước kiểm định triển khai. Khi dịch vụ bận, trả `Retry-After`; khi mất kết nối, hiện lỗi tiếng Việt và giữ nguyên nội dung nhập.

Các nhãn địa chỉ được lưu cùng TripRequest/booking sau lựa chọn; độ dài tối đa 500 ký tự. Không cần migration database vì chúng nằm trong cột JSON hiện có. Việc định giá và ký quỹ không thay đổi.

## Bằng chứng kiểm tra

- Toàn bộ backend: **94/94** ở lượt chính; sau bổ sung TTL/quota, bộ geocoding riêng **10/10**, coverage hai module geocoding/API **89%**. [JUnit toàn bộ](../artifacts/address-search/validation-v1/python-tests.xml), [JUnit geocoding](../artifacts/address-search/validation-v1/geocoding-tests.xml).
- Frontend unit: **19/19**, gồm nhập chưa xác định vị trí, kết quả đến muộn, chọn kết quả bằng Enter và xác nhận địa chỉ thủ công.
- Browser regression: **14/14**, gồm kiểm tra payload tọa độ/nhãn, chặn dùng vị trí cũ khi tra cứu thất bại, xác nhận địa chỉ thủ công và đổi chiều hai địa chỉ.
- Đã nhập hai địa chỉ thực `144 Xuân Thủy, Hà Nội` và `1 Đại Cồ Việt, Hà Nội` qua UI, chọn kết quả Photon thật rồi tạo TripRequest thành công HTTP 201. Tọa độ và nhãn gửi sang backend khớp lựa chọn; không tạo booking hoặc thanh toán. [Kết quả thật](../artifacts/address-search/live-v1/results.json), [ảnh kết quả tìm địa chỉ](../artifacts/address-search/live-v1/destination-results.png).

Địa chỉ trong các lượt kiểm tra thật là địa chỉ trường đại học công khai; không dùng địa chỉ nhà riêng hoặc dữ liệu khách hàng.

Lượt cuối [live-v4](../artifacts/address-search/live-v4/results.json) kiểm tra lại sau chỉnh bố cục nút đổi điểm và cập nhật kích thước bản đồ khi danh sách mở/đóng; [axe](../artifacts/address-search/live-v4/accessibility.json) không phát hiện vi phạm tự động trên form khi mở kết quả của cả hai ô, còn mục cần đánh giá thủ công được ghi riêng. [Ảnh giao diện mới](../artifacts/address-search/live-v4/selected-addresses.png). Đây là kiểm tra chức năng local, không phải chứng nhận mọi số nhà đều có trong dữ liệu hoặc WCAG đầy đủ.
