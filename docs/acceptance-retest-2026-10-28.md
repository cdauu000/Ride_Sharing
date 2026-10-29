# Báo cáo kiểm thử lại sau sửa lỗi — bản review local v2

**Kết luận:** bản local sẵn sàng để chủ dự án trực tiếp kiểm thử tại **http://127.0.0.1:3020**. Bộ UAT đã định nghĩa đạt **31/31**, gồm 25 kịch bản ban đầu và 6 nhánh bổ sung. Điều này chưa phải chứng nhận toàn bộ MUST + SHOULD trên hạ tầng và dữ liệu thực.

Ngày thực hiện: 28/10/2026, giờ Việt Nam. [Hướng dẫn kiểm thử trực tiếp](direct-testing.md) nêu tài khoản, cách chạy lại và số tiền mong đợi. Bản review dùng `artifacts/review/rise.db` và `escrow.db`, đồng hồ thực, khác database đã chạy nghiệm thu.

## Những gì đã sửa

| Phát hiện cũ | Thay đổi và bằng chứng hồi quy |
|---|---|
| F01 — Offer thiếu thông tin | Điểm đón/trả có tên và tọa độ; số ghế, giờ đón, quãng đường/thời gian, thu nhập và ước tính theo giờ. Thu nhập Pool thể hiện điều kiện ghép và phương án không ghép. Điểm dừng và booking cũng có vị trí. Kiểm tra quyền sở hữu/vai trò và chia sẻ công khai không lộ vị trí mới. |
| F02 — giữ menu cũ | Xóa menu khi thay đổi ý định, tìm lại hoặc gặp lỗi; bỏ phản hồi tìm kiếm đến muộn; vô hiệu hóa phương án hết hạn. Browser regression chủ động trả 429 cho lần tìm tiếp theo và xác nhận không còn thẻ cũ. |
| F03 — giới hạn truy cập | Hạn mức đọc/ghi theo người có JWT đã xác minh; hạn mức IP riêng chống lạm dụng; login vẫn có giới hạn theo IP. Polling tôn trọng Retry-After và nút thử lại đếm ngược. Đọc quá hạn không chặn đăng xuất. Unit/API test kiểm tra dùng chung IP và JWT giả. |
| F04 — tràn màn hình | Sửa kích thước tối thiểu của grid, bảng cuộn, form và điểm dừng. Cả hành khách lẫn tài xế không tràn ở 375/768/1440 px trong lượt cuối. |
| F05 — accessibility | Tăng tương phản và vùng chạm, kể cả nhãn lịch sử booking phát hiện khi kiểm lại. Axe không phát hiện vi phạm tại ba màn hình riêng: lịch sử hành khách, tìm chuyến và tài xế. Các mục cần đánh giá thủ công vẫn được giữ trong kết quả axe. |
| F06 — mã lỗi kỹ thuật | Thông báo tiếng Việt và hướng dẫn khắc phục; validation chỉ rõ trường nhập; không hiển thị nội dung lỗi máy chủ tùy ý bằng tiếng Anh. |
| F07 — hoàn tiền khi chưa thu | Hủy HELD chưa ký quỹ giữ NONE/“Chưa ký quỹ”, không tạo receipt hoặc payout hoàn tiền giả. |
| F08 — bắt đầu quá sớm | UI dùng điều kiện sẵn sàng do backend cung cấp và giờ khởi hành; nút no-show cũng chờ đủ bằng chứng/hạn hợp lệ. Backend vẫn kiểm tra độc lập. |
| F09 — đếm ngược sai khi tiến đồng hồ | Đồng bộ giờ server qua header/API; đếm ngược Offer và các cổng thời gian dùng cùng đồng hồ. UAT kiểm tra Offer vẫn còn 1–60 giây sau nhiều ngày demo. |
| Phát hiện thêm — cấu hình tài xế tải chậm | Chưa hiện form để chỉnh khi dữ liệu chưa tải; refresh nền giữ thay đổi chưa lưu, lưu thành công xóa trạng thái nháp. Browser regression kiểm tra cả tải chậm và refresh nền. |
| Bản đồ mất kết nối | Thông báo nền bản đồ không tải; giữ điểm chọn/tọa độ và ngừng yêu cầu tile khi lỗi. Có browser regression mất tile. |

Luồng tài chính giữ đúng baseline. Không đổi tỷ lệ hoa hồng hay ngưỡng thời gian để làm test đạt. Script khởi động local tăng thời gian giữ kết nối backend lên 30 giây; lượt cuối không lặp lại lỗi reset kết nối proxy từng quan sát ở lượt dò trước, nhưng chưa có kết luận tải production.

## Kiểm chứng đã thực thi

| Kiểm tra | Kết quả và phạm vi |
|---|---|
| Toàn bộ pytest | **85/85**; [JUnit](../artifacts/acceptance/uat-fixed-v4/python-tests.xml) |
| Công cụ đối soát bổ sung | **1/1**: phát hiện chênh lệch Quỹ thay vì báo đạt giả; được chạy riêng sau lượt pytest trên |
| Frontend unit | **15/15**, gồm retry idempotency sau 5xx, Retry-After, phản hồi tìm kiếm đến muộn và đồng hồ demo |
| Browser regression dùng mock | **6/6**, gồm menu cũ khi 429, cấu hình tải chậm/refresh, bản đồ mất mạng |
| Browser với API/worker thật | **31/31**, **0 BLOCKED**, 0 JavaScript runtime, 0 HTTP 5xx, 0 HTTP 429 trong lượt cuối |
| Solidity/EVM | **19/19**, chạy lại local; không deploy bên ngoài |
| Kiểm tra tĩnh/build | Ruff, TypeScript, Prettier đạt; build Next production thành công, cấu hình review không tạo output standalone |
| Responsive | Không tràn ở 6 tổ hợp vai trò × chiều rộng |
| Axe 4.14 | 0 vi phạm tự động trên 3 màn hình; còn mục “incomplete” cần người kiểm tra, chưa chứng nhận WCAG đầy đủ |

Nguồn kết luận UI: **duy nhất lượt `uat-fixed-v4`**. Các lượt `v2`, `v3` được giữ làm lịch sử dò lỗi, không gộp chọn các ca đạt để tạo kết quả 31/31. Trong `v3`, form cấu hình tải chậm làm UAT-15 thất bại và chặn 5 ca phụ thuộc; lỗi này đã được sửa và chạy lại toàn bộ trên database mới. Một lỗi proxy 500 trong lượt đó cũng được ghi nhận, không xóa khỏi báo cáo thô.

## Các nhánh bổ sung đã đi qua giao diện

| ID | Nhánh | Kết quả tiền thực tế |
|---|---|---|
| UAT-26 | No-show sau đủ thời gian | Phí 16.200; hoàn 64.800 từ cước 81.000 |
| UAT-27 | Tài xế báo sự cố trước đón | Hoàn đủ 194.000, không thu phí khách |
| UAT-28 | Hủy bao xe nội đô sau ân hạn | Phí trần 20.000; hoàn 174.000 |
| UAT-29 | Tài xế từ chối khách ghép | Khách gốc trả 155.000; tài xế 131.750; bảo đảm Quỹ 0; khách bị từ chối nhận hoàn ký quỹ |
| UAT-30 | Liên tỉnh đủ 3 ghế tự nhiên | Tổng 600.000; tài xế 540.000; hoa hồng 10% |
| UAT-31 | Từ chối góp thêm, tài xế tự nguyện RUN | Giữ giá 200.000; tài xế 180.000; không ép khách góp thêm |

25 ca ban đầu cũng được chạy lại: đăng nhập/đăng ký, validation, các loại dịch vụ, hủy trước/sau ký quỹ, chia sẻ/SOS, xe máy/bao xe/Pool, chuyển Offer, private liên tỉnh, góp thêm, chặn đi sớm, hoàn tiền thiếu khách, bàn phím, responsive và thông tin Offer. [Chi tiết từng ca và ảnh](../artifacts/acceptance/uat-fixed-v4/results.json).

## Đối soát sau khi dừng worker nghiệm thu

Database có **11 booking hoàn thành**, 1 no-show và các booking hủy theo kịch bản. Tổng tiền cước/phí thực thu trong payout là **2.961.200 VND**, gồm cả phí hủy và no-show. Không cộng tiền ký quỹ đã hoàn vào doanh thu.

| Khoản | VND |
|---|---:|
| Tổng thực thu | 2.961.200 |
| Quỹ chi bảo đảm | 7.300 |
| Tổng tài xế nhận | 2.548.760 |
| Nền tảng nhận ròng | 412.300 |
| Đóng góp Quỹ | 7.440 |

**2.961.200 + 7.300 = 2.548.760 + 412.300 + 7.440.** Mọi payout cân bằng độc lập. Quỹ database = journal = tổng sổ cái = **5.000.140**. 128 job hoàn thành, 2 job chờ thời điểm tương lai, không có FAILED_RETRY hoặc DEAD_LETTER. Các khoản tiền là local simulation; transaction hash không bị giả thành giao dịch blockchain.

[Đối soát máy đọc được](../artifacts/acceptance/uat-fixed-v4/financial-evidence.json), [responsive](../artifacts/acceptance/uat-fixed-v4/responsive.json), [axe](../artifacts/acceptance/uat-fixed-v4/accessibility.json), [tổng hợp UAT](../artifacts/acceptance/uat-fixed-v4/summary.json).

## Những giới hạn vẫn còn

Chưa chạy PostgreSQL/PostGIS và hai graph OSRM thật trên máy này; chưa xác nhận vùng địa lý/xe máy bằng dữ liệu thực. Chưa có khảo sát người thật, kiểm thử chuyến xe/GPS thực địa, thiết bị di động thật, trình đọc màn hình, mọi nhánh gộp liên tỉnh qua UI hoặc ma trận tải/nghiên cứu main nhiều seed. Testnet được hoãn theo chỉ đạo của bạn. KYC/SOS vẫn là mô phỏng.

Do đó kết luận là **đạt bộ kiểm thử local và sẵn sàng cho bạn test**, không phải cam kết phần mềm không thể phát sinh lỗi hoặc toàn bộ MUST/SHOULD đã nghiệm thu trên môi trường đích. [Ma trận yêu cầu](requirements.md) giữ rõ từng phần cần dữ liệu/hạ tầng tiếp theo.
