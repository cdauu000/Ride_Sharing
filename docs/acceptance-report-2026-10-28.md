# Báo cáo nghiệm thu hành khách và tài xế

Đây là báo cáo trước sửa lỗi, được giữ làm lịch sử. Bản cập nhật và bằng chứng kiểm thử lại nằm tại [báo cáo sau sửa](acceptance-retest-2026-10-28.md).

**Ngày kiểm thử: 28/10/2026 — múi giờ Việt Nam.**

**Kết luận: CHƯA ĐẠT NGHIỆM THU TOÀN BỘ.** Các luồng nghiệp vụ chính đã chạy được tại local và số tiền ở các ca đã kiểm tra khớp baseline. Tuy nhiên, giao diện nhận chuyến của tài xế còn thiếu thông tin bắt buộc; giao diện có thể giữ gợi ý của tuyến cũ khi tìm kiếm lỗi; màn hình nhỏ và khả năng truy cập còn vấn đề.

Có **25 kịch bản riêng biệt: 22 đạt tiêu chí chức năng, 3 chưa đạt** — responsive tài xế, tiêu chí accessibility và thông tin Offer. Không ghi nhận lỗi JavaScript runtime hoặc HTTP 5xx trong các đợt chính. Đây không phải kết luận hệ thống không còn lỗi.

## 1. Môi trường và phương pháp

- Giao diện Next.js 16.4.3 đã build production; Chrome 156.0.8078.48, Playwright điều khiển thao tác như người dùng. API FastAPI thật, SQLite riêng, worker thật, model `ltr_v9_main_v1`.
- Dùng tài khoản demo riêng theo vai trò và các browser context tách biệt. Các hành động đặt, nhận/từ chối, đón/trả, hủy, đánh giá và góp thêm được thực hiện qua giao diện; API đọc và sổ cái được dùng để đối chiếu độc lập.
- Routing là **fixture minh họa**; tiền là **ký quỹ local**, không có tiền thật hoặc giao dịch testnet. Xác nhận điểm dừng kiểm tra vòng đời phần mềm, không phải chuyến xe/GPS ngoài thực địa.
- Địa chỉ QA là `http://127.0.0.1:3020`, API `8020`; database và journal nằm trong thư mục nghiệm thu riêng. Các mốc T−72h/T−24h dùng nút đồng hồ demo của Admin.
- Production build dùng bộ dependency local đầy đủ. Lượt này không kiểm chứng image Docker hoặc khả năng phân phối standalone. Bản copy dùng junction dependency nên build có cảnh báo tracing; không tính cảnh báo này thành lỗi chức năng ứng dụng.
- Dữ liệu kết luận lấy từ các đợt `04`, `05`, `07`, `08`. Các lần dò selector và điều chỉnh kỳ vọng của bộ kiểm thử được giữ riêng, không tính thành lỗi sản phẩm. Bao xe nội đô được đối chiếu đúng hoa hồng **20%**, liên tỉnh private/topup **15%**.

Các ca chạy lại được ghi rõ: liên tỉnh được chạy theo đợt riêng sau khi lượt thao tác dồn gặp rate limit; chốt hành trình được chờ đủ điểm dừng mới nhất; sau tải lại trang, chọn lại khu vực tài xế qua điều hướng. Không thay cấu hình giới hạn API hoặc sửa mã nghiệp vụ để làm ca kiểm thử đạt.

## 2. Ma trận kết quả

“Đạt” chỉ áp dụng cho tiêu chí của từng ca và môi trường vừa nêu. UAT-22 đã thực thi axe thành công nhưng **không đạt cổng accessibility** vì còn vi phạm; trạng thái đánh giá khác trạng thái thực thi công cụ. Báo cáo thô được giữ nguyên.

| ID | Kịch bản | Kết quả | Minh chứng |
|---|---|---|---|
| UAT-01 | Khởi động và đăng nhập đúng vai trò | Đạt | [Xem](../artifacts/acceptance/uat-20261028-08/screenshots/UAT-01.png) |
| UAT-02 | Đăng nhập sai mật khẩu bị từ chối | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-02.png) |
| UAT-03 | Đăng ký hành khách mới trên giao diện | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-03.png) |
| UAT-04 | Kiểm tra lỗi ngân sách và điểm đón trùng điểm đến | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-04.png) |
| UAT-05 | Tìm chuyến, xem đủ ba dịch vụ và ba mức giá Pool | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-05.png) |
| UAT-06 | Hành lý lớn và hai hành khách loại xe máy | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-06.png) |
| UAT-07 | Hủy khi tài xế chưa nhận, không phát sinh tiền | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-07.png) |
| UAT-08 | Đặt xe máy và tài xế nhận offer thật | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-08.png) |
| UAT-09 | Chia sẻ hành trình và SOS mô phỏng | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-09.png) |
| UAT-10 | Tài xế đến điểm đón, không phạt no-show sớm | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-10.png) |
| UAT-11 | Hoàn tất xe máy, đúng cước, thu nhập và đánh giá | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-11.png) |
| UAT-12 | Bao xe nội đô bốn người và hoàn tất | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-12.png) |
| UAT-13 | Pool hai ghế cùng booking vẫn là không ghép | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-13.png) |
| UAT-14 | Pool hai hành khách độc lập, khóa giá và đối soát | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-14.png) |
| UAT-15 | Tài xế từ chối, chuyển offer; khách hủy sau ký quỹ | Đạt | [Xem](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-15.png) |
| UAT-16 | Bao xe liên tỉnh đi ngay và thanh toán | Đạt | [Xem](../artifacts/acceptance/uat-20261028-05/screenshots/UAT-16.png) |
| UAT-17 | Tài xế đăng ghép liên tỉnh và hành khách đặt hai ghế | Đạt | [Xem](../artifacts/acceptance/uat-20261028-05/screenshots/UAT-17.png) |
| UAT-18 | Thiếu ghế: hành khách đồng ý góp thêm tự nguyện | Đạt | [Xem](../artifacts/acceptance/uat-20261028-05/screenshots/UAT-18.png) |
| UAT-19 | Liên tỉnh chốt thứ tự, chặn đi sớm, hoàn tất đúng tiền | Đạt | [Xem](../artifacts/acceptance/uat-20261028-07/screenshots/UAT-19.png) |
| UAT-20 | Từ chối góp thêm, tài xế hủy và hoàn tiền | Đạt | [Xem](../artifacts/acceptance/uat-20261028-07/screenshots/UAT-20.png) |
| UAT-21 | Giao diện hành khách và tài xế ở ba kích thước | **Chưa đạt** | [Xem](../artifacts/acceptance/uat-20261028-08/screenshots/UAT-21-driver-375.png) |
| UAT-22 | Audit tự động khả năng truy cập | **Chưa đạt** | [Xem](../artifacts/acceptance/uat-20261028-08/accessibility.json) |
| UAT-23 | Đăng xuất và ngăn đọc lại dữ liệu riêng | Đạt | [Xem](../artifacts/acceptance/uat-20261028-08/screenshots/UAT-23.png) |
| UAT-24 | Điều hướng tài xế bằng bàn phím | Đạt | [Xem](../artifacts/acceptance/uat-20261028-08/screenshots/UAT-24.png) |
| UAT-25 | Thông tin quyết định nhận offer của tài xế | **Chưa đạt** | [Xem](../artifacts/acceptance/uat-20261028-07/screenshots/UAT-25-offer.png) |

## 3. Đối soát tiền thực tế

Đơn vị: VND. Thu nhập tài xế ở Pool không ghép bao gồm phần Quỹ bù.

| Luồng đã hoàn tất qua UI | Khách trả | Tài xế nhận | Nền tảng | Quỹ tăng/giảm |
|---|---:|---:|---:|---:|
| Xe máy nội đô | 81.000 | 64.800 | 16.200 | 0 |
| Bao xe nội đô, 4 người | 194.000 | 155.200 | 38.800 | 0 |
| Pool không ghép, 2 ghế cùng booking | 174.000 | 155.200 | 26.100 | −7.300 |
| Pool A+B, hai booking độc lập | 248.000 = 143.000 + 105.000 | 210.800 | 29.760 | +7.440 |
| Bao xe liên tỉnh NOW | 637.000 | 541.450 | 95.550 | 0 |
| Liên tỉnh, 2 ghế góp thêm tự nguyện | 636.000 | 540.600 | 95.400 | 0 |

Tổng cước của 7 booking hoàn thành: **1.970.000**. Tổng tài xế nhận: **1.668.050**; nền tảng **301.810**; đóng góp Quỹ **7.440**; Quỹ bù **7.300**. Kiểm tra bảo toàn: **1.970.000 + 7.300 = 1.668.050 + 301.810 + 7.440**.

Đã kiểm tra thêm: hủy trước nhận chuyến phí 0, hủy private sau ký quỹ trong ân hạn hoàn 194.000, từ chối góp thêm rồi tài xế hủy hoàn 200.000. Hủy trước ký quỹ không có receipt/payout, dù UI đang dùng nhãn REFUNDED.

Đợt `04`: Quỹ DB = journal = tổng ledger = **5.000.140**. Đợt `05`: cả ba bằng **5.000.000**. Hai đợt là hai database độc lập, không phải số dư trước/sau của cùng một Quỹ. Chín bản ghi payout, gồm cả hủy phí 0, đều khớp phương trình tiền; không có transaction hash giả. [Dữ liệu đối soát](../artifacts/acceptance/report-20261028/financial-evidence.json).

## 4. Các vấn đề cần quyết định xử lý

P1: ảnh hưởng trực tiếp quyết định/tác nghiệp, cần sửa trước nghiệm thu hoàn tất. P2: ảnh hưởng sử dụng hoặc vận hành đáng kể. P3: thông báo/trạng thái hoặc tiện ích demo. Các mức này là phân loại nghiệm thu, không phải xác nhận lỗ hổng bảo mật.

| Mã | Mức | Phát hiện và ảnh hưởng | Bằng chứng |
|---|---|---|---|
| F01 | **P1** | Offer chỉ có loại dịch vụ, mã booking, đếm ngược và nút nhận/từ chối; thiếu điểm đón/trả, thu nhập dự kiến và thu nhập/giờ. Người lái chưa có đủ thông tin để quyết định nhận. Màn hình điểm dừng cũng chỉ ghi “Đón khách/Trả khách” và mã booking. Chưa đáp ứng T2 trong Revision 9. | [Offer](../artifacts/acceptance/uat-20261028-07/screenshots/UAT-25-offer.png), [hành trình tài xế](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-08.png); đặc tả gốc dòng 2948 |
| F02 | **P1** | Đổi điểm đến sang Hưng Yên, tìm kiếm gặp 429, nhưng các thẻ nội đô của lần tìm trước vẫn còn nút “Chọn chuyến”. Có rủi ro chọn nhầm ý định/tuyến cũ. Chưa thực hiện booking nhầm để tạo tác động; điều đã xác nhận là menu cũ còn khả dụng trên UI. | [Form liên tỉnh nhưng menu nội đô](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-16-failure-passenger.png) |
| F03 | **P2** | Lượt nhiều phiên/thao tác nhanh trên cùng IP gặp 10 phản hồi 429 trong đợt 04, gồm tìm chuyến và polling. Chạy liên tỉnh theo đợt riêng đạt, không đổi limiter. Cần đánh giá polling, xử lý Retry-After và người dùng chung NAT; chưa coi đây là benchmark tải production. | [Log đợt 04](../artifacts/acceptance/uat-20261028-04/results.json), [đợt 05 không có 429](../artifacts/acceptance/uat-20261028-05/results.json) |
| F04 | **P2** | Viewport tài xế 375 px có nội dung rộng **437 px**, tràn 62 px. 768/1440 px đạt; hành khách đạt cả ba kích thước. | [Ảnh 375 px](../artifacts/acceptance/uat-20261028-08/screenshots/UAT-21-driver-375.png), [số đo](../artifacts/acceptance/uat-20261028-08/responsive.json) |
| F05 | **P2** | Axe 4.14.0 phát hiện `color-contrast` ở hai màn hình và `target-size` ở form hành khách, impact “serious”. Các vị trí gồm chữ nhỏ/nhãn và vùng chọn điểm/tọa độ. Chưa đạt cổng accessibility; không chứng nhận WCAG chỉ bằng công cụ này. | [Chi tiết từng phần tử](../artifacts/acceptance/uat-20261028-08/accessibility.json) |
| F06 | P3 | Một số lỗi vẫn hiển thị mã kỹ thuật như `NO_SHOW_WAIT_NOT_MET`, `RATE_LIMITED`, `TRIP_NOT_READY_TO_DEPART`; người dùng khó biết phải làm gì tiếp. | [No-show trước hạn](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-10.png) |
| F07 | P3 | Hủy HELD khi chưa nạp tiền vẫn gán/hiển thị REFUNDED. Không có chi sai được phát hiện, nhưng người dùng có thể tưởng đã thu và hoàn tiền. | [Hủy trước nhận](../artifacts/acceptance/uat-20261028-04/screenshots/UAT-07.png) |
| F08 | P3 | Nút “Bắt đầu chuyến” liên tỉnh bật trước giờ khởi hành. Backend chặn đúng, nên không có chuyến xuất phát sớm; UI nên thể hiện điều kiện còn thiếu. | UAT-19 trong [đợt 07](../artifacts/acceptance/uat-20261028-07/results.json) |
| F09 | P3, chỉ demo | Sau khi Admin tiến đồng hồ khoảng 5 ngày, offer vốn có hạn 20 giây lại hiển thị khoảng **431.900 giây** vì UI so với đồng hồ máy. Cần đồng bộ cách hiển thị với server trong chế độ demo. Chưa quan sát vấn đề này khi đồng hồ không tăng tốc. | [Offer sau tiến đồng hồ](../artifacts/acceptance/uat-20261028-07/screenshots/UAT-25-offer.png) |

### Bước tái hiện hai vấn đề P1

**F01:** hành khách chọn Phenikaa → Đống Đa, chọn bao xe; mở màn hình tài xế trước khi nhận. Kiểm tra những thông tin có trên Offer và đối chiếu T2. Ca UAT-25 đã chụp Offer rồi hủy booking thử, không nhận tiền.

**F02:** tìm nội đô để có menu; đổi điểm đến sang Hưng Yên; khi tìm kiếm mới bị rate limit, quan sát form đã đổi nhưng thẻ cũ vẫn bấm chọn được. Đợt kiểm thử đã ghi đúng điều kiện lỗi; chưa kết luận tình trạng này xảy ra với mọi loại lỗi hoặc đã gây booking nhầm trong thực tế.

## 5. Phạm vi còn chưa kiểm chứng

- Không có chuyến xe hoặc GPS thực; không chạy OSRM/PostGIS, testnet, finality hay lỗi RPC trong đợt nghiệm thu này.
- Chưa kiểm đầy đủ mọi nhánh: liên tỉnh đủ ngưỡng tự nhiên, gộp hai chuyến, tài xế RUN dưới ngưỡng, phí hủy muộn, no-show sau đủ thời gian, driver abort và từ chối ghép trên UI.
- Mobile là viewport Chromium desktop 375/768/1440 px, chưa phải thiết bị Android/iOS thật hoặc kiểm thử Safari/Firefox.
- Có kiểm tra Tab/Enter qua điều hướng; chưa kiểm trình đọc màn hình hay toàn bộ WCAG. Hai nhãn `passenger`/`passenger-plan` trong audit cuối cùng cùng là form tìm chuyến, không được coi là hai màn hình độc lập.
- Không đo Core Web Vitals/INP đại diện hay SLA tải; số đo ở các đợt local không thay kết luận hiệu năng production.
- Không có khảo sát người thật hoặc đánh giá độ chính xác AI từ đợt này. Kết quả UAT không chứng minh hòa vốn Quỹ.

## 6. Đề xuất cho quyết định tiếp theo

Ưu tiên nghiệm thu phần thông tin Offer/điểm dừng và việc vô hiệu hóa menu cũ khi ý định tìm kiếm thay đổi hoặc thất bại. Sau đó xử lý mobile, accessibility và trải nghiệm khi gặp rate limit, rồi chạy lại đúng bộ UAT này. Các sửa chức năng này **chưa được áp dụng** trong lượt lập báo cáo.

Các con số tiền đã đạt không đủ để bỏ qua các thiếu hụt sử dụng ở trên. Khi các điểm chặn đã được giải quyết, vẫn cần các kiểm định hạ tầng và nhánh chưa chạy trước khi nghiệm thu đầy đủ MUST + SHOULD.

## 7. Bằng chứng và tái lập

- [Bảng đánh giá máy đọc được](../artifacts/acceptance/report-20261028/acceptance-assessment.json).
- [Đối soát tiền](../artifacts/acceptance/report-20261028/financial-evidence.json), [hash mã được kiểm thử](../artifacts/acceptance/report-20261028/source-fingerprint.json), [kiểm tra thay đổi](../artifacts/acceptance/report-20261028/change-audit.json).
- Script: `web/tests/acceptance-live.cjs`. Biến `UAT_BASE_URL`, `UAT_OUTPUT`, `UAT_AXE_PATH`; tùy chọn `UAT_CASES` để chia đợt. Chọn database/output mới, chạy `init-demo`, API/worker và frontend proxy cùng môi trường trước khi chạy script từ thư mục `web`. Không trỏ vào dữ liệu thật.
- Raw JSON và ảnh nằm trong `artifacts/acceptance/uat-20261028-{04,05,07,08}`. Mật khẩu, cookie và journal/database không đưa vào gói báo cáo.
- Không sửa mã nghiệp vụ trong lượt QA. Có thêm script/báo cáo; `web/next-env.d.ts` khác bản release ở tham chiếu type `.next/dev` do Next tự sinh. Không dùng thay đổi tự sinh này để kết luận đã sửa lỗi chức năng.

**Trạng thái bàn giao báo cáo: đã hoàn tất kiểm thử và ghi nhận kết quả; chờ chủ dự án quyết định công việc tiếp theo.**
