# Chỉ mục bằng chứng đặc tả

Mỗi tệp gốc được đọc toàn bộ để lập chỉ mục, mã băm và đối chiếu cấu trúc. Chỉ mục không thay thế báo cáo phân tích và bằng chứng kiểm thử.

## bao_cao_tien_du_an_ride_sharing_revision_9.md

3834 dòng; 412949 bytes; SHA-256 `edbf0e9923bbcd933dc5586613abd5a3cb7dd7e7f0ae75049b3fffecd6380016`.

| Dòng | Nội dung |
|---:|---|
| 1 | BÁO CÁO TIỀN DỰ ÁN — REVISION 9 |
| 3 | XÂY DỰNG NỀN TẢNG ĐẶT XE THÔNG MINH ĐA DỊCH VỤ (XE MÁY, TAXI BAO XE, TAXI GHÉP NỘI ĐÔ VÀ LIÊN TỈNH) VỚI ĐỊNH GIÁ GHÉP CÔNG BẰNG, GỢI Ý CHUYẾN BẰNG AI VÀ KÝ QUỸ BLOCKCHAIN |
| 24 | TÓM TẮT THAY ĐỔI SO VỚI REVISION 8 (REVISION 8 → REVISION 9) |
| 42 | MỤC LỤC |
| 150 | PHẦN 0 — ĐỀ TÀI, MỤC TIÊU NGHIÊN CỨU VÀ PHÂN LOẠI PHẠM VI |
| 152 | 0.1. ĐỀ TÀI VÀ ĐÓNG GÓP NGHIÊN CỨU – KỸ THUẬT |
| 154 | Tên đề tài |
| 170 | Đóng góp dự kiến của đề tài và Ma trận ánh xạ kiểm chứng |
| 192 | 0.2. PHÂN LOẠI PHẠM VI (MoSCoW) VÀ TỶ TRỌNG CÔNG SỨC |
| 201 | Hạng mục MUST (Bắt buộc) |
| 220 | Hạng mục SHOULD (Khuyến nghị thực hiện) |
| 234 | Hạng mục COULD (Mở rộng tùy chọn) |
| 250 | Hạng mục WON'T (Không thực hiện trong đồ án này) |
| 263 | Tỷ trọng phân bổ công sức dự kiến |
| 276 | PHẦN I — TỔNG QUAN BÀI TOÁN, ĐỐI TƯỢNG SỬ DỤNG VÀ MA TRẬN NĂM DỊCH VỤ |
| 278 | 1. PHÂN TÍCH BÀI TOÁN THỰC TẾ VÀ NHU CẦU NGƯỜI DÙNG |
| 299 | 2. MA TRẬN NĂM DỊCH VỤ VÀ QUY TẮC PHÂN LOẠI KHÔNG GIAN – THỜI GIAN |
| 301 | 2.1. Ma trận năm dịch vụ |
| 313 | 2.2. Luật thời gian đặt theo từng dịch vụ |
| 326 | 2.3. Quy tắc tự động xác định Nội đô (`URBAN`) và Liên tỉnh (`INTERCITY`) kèm xử lý biên không gian (`[ACCEPTED]` — D-20, D-50) |
| 356 | 2.4. Cơ chế tìm xe và điều phối theo từng dịch vụ |
| 367 | 3. CÁC VAI TRÒ VÀ QUYỀN HẠN TRONG HỆ THỐNG |
| 387 | 4. LUỒNG NGHIỆP VỤ TỔNG QUÁT THEO TỪNG NHÓM DỊCH VỤ |
| 389 | 4.1. Luồng đặt xe Nội đô (`BIKE_URBAN`, `CAR_URBAN_PRIVATE`, `CAR_URBAN_POOL`) |
| 427 | 4.2. Luồng đặt Taxi bao xe liên tỉnh (`CAR_INTERCITY_PRIVATE`) |
| 447 | 4.3. Luồng đặt Taxi ghép liên tỉnh (`CAR_INTERCITY_POOL`) |
| 482 | 5. KIẾN TRÚC HỆ THỐNG MỨC CAO (MODULAR MONOLITH) |
| 517 | PHẦN II — QUY TẮC NGHIỆP VỤ CHUNG, RÀNG BUỘC CỨNG VÀ VÒNG ĐỜI TRẠNG THÁI |
| 519 | 6. TRIP INTENT VÀ QUY TẮC SUY DIỄN TẬP DỊCH VỤ HỢP LỆ |
| 542 | Quy tắc suy diễn tập dịch vụ hợp lệ (`allowed_service_codes`) |
| 558 | 7. HỆ THỐNG 11 RÀNG BUỘC CỨNG (HARD CONSTRAINTS) |
| 619 | 8. QUY TẮC NGÂN SÁCH (CỨNG VÀ MỀM) |
| 631 | 9. HỆ THỐNG MÁY TRẠNG THÁI TRỰC GIAO (ORTHOGONAL STATE MACHINES) |
| 637 | 9.1. Trục 1 — Trạng thái hành trình của Booking (`ride_status`) |
| 657 | 9.2. Trục 2 — Trạng thái ghép và chốt giá của Booking (`price_status`) |
| 677 | 9.3. Trục 3 — Trạng thái ký quỹ Blockchain (`escrow_status`) |
| 711 | PHẦN III — NỘI ĐÔ: XE MÁY, TAXI BAO XE, TAXI GHÉP VÀ MÔ HÌNH ĐỊNH GIÁ – KINH TẾ |
| 713 | 10. BA DỊCH VỤ NỘI ĐÔ VÀ CƠ CHẾ TOP-K ĐA PHƯƠNG TIỆN |
| 717 | 10.1. Xe máy nội đô (`BIKE_URBAN`) — Chạy 1:1 |
| 736 | 10.2. Taxi bao xe nội đô (`CAR_URBAN_PRIVATE`) |
| 740 | 10.3. Taxi ghép nội đô (`CAR_URBAN_POOL`) |
| 744 | 10.4. Ví dụ đối sánh ba dịch vụ nội đô trên cùng một nhu cầu di chuyển |
| 755 | 10.5. Cơ chế xếp hạng Top-K đa phương tiện (`[ACCEPTED]` — D-40) |
| 766 | 11. HÌNH THỨC ĐẶT, CỬA SỔ GHÉP ĐỘNG VÀ ĐIỂM KHÓA GIÁ (`pool_lock_point`) |
| 793 | 12. GIÁ THAM CHIẾU TAXI BAO XE NỘI ĐÔ VÀ HỆ SỐ GHẾ CHO NHÓM 2 KHÁCH |
| 795 | 12.1. Công thức giá Taxi bao xe nội đô (`CAR_URBAN_PRIVATE`) |
| 815 | 12.2. Quy tắc định giá Booking 2 ghế (`seat_count = 2`) trong Taxi ghép nội đô không mâu thuẫn với chính sách giá (`[ACCEPTED]` — D-45b / O-04) |
| 849 | 13. GIÁ CỦA CẢ CHUYẾN GHÉP (`PlanFare`) |
| 873 | 14. ĐIỀU KIỆN KHẢ NĂNG CHIA SẺ (SHAREABILITY) VÀ RÀNG BUỘC SINH LỜI TÀI XẾ |
| 877 | 14.1. Cổng 1 — Điều kiện lợi ích tối thiểu của hành khách (Passenger Shareability Condition — `[ACCEPTED]` D-16) |
| 889 | 14.2. Cổng 2 — Điều kiện bảo toàn tốc độ sinh lời của tài xế tính trên Khoản Payout thực tế sau làm tròn (`[ACCEPTED]` D-45a / O-03) |
| 920 | 15. MÔ HÌNH PHÂN BỔ GIÁ GHÉP THEO TRỌNG SỐ BẤT TIỆN CÓ CHẶN HAI ĐẦU (`Floor_i` & `Cap_i`) VÀ CHÈN KHÁCH ĐỘNG |
| 924 | 15.1. Năm nguyên tắc định giá công bằng đã hiệu chỉnh (`[ACCEPTED]`) |
| 954 | 15.2. Công thức trọng số bất tiện (có điều chỉnh theo số ghế) và phân bổ cơ sở |
| 981 | 15.3. Cận trên (`Cap_i`), Cận dưới (`Floor_i`), Điều kiện khả thi và Thuật toán phân bổ hai cận chính xác (`[ACCEPTED]` — D-43) |
| 983 | 15.3.1. Tại sao bắt buộc phải có cả Cận trên (`Cap_i`) và Cận dưới (`Floor_i`)? |
| 988 | 15.3.2. Định nghĩa Cận trên hiệu dụng (`EffectiveCap_i`) và Cận dưới (`Floor_i`) |
| 1003 | 15.3.3. Điều kiện cần và đủ để tồn tại nghiệm (Feasibility Theorem) & Xử lý khi vô nghiệm |
| 1027 | 15.3.4. Thuật toán phân bổ hai cận chính xác theo Điểm gãy đơn điệu (Exact Piecewise-Linear Breakpoint Water-Filling) |
| 1062 | 15.4. Quy tắc làm tròn tiền thu của hành khách (`[ACCEPTED]` — D-18) |
| 1070 | 15.5. Hệ điều kiện đầy đủ và Quy trình định giá khi chèn thêm khách động lúc xe đang chạy (`[ACCEPTED]` — D-44 / O-02) |
| 1127 | 16. KIỂM CHỨNG ĐỊNH LƯỢNG: VÍ DỤ CHUẨN PHENIKAA → ĐỐNG ĐA VÀ CÁC KỊCH BẢN BIÊN |
| 1131 | 16.1. Kịch bản chuẩn 2 hành khách: Phenikaa → Đống Đa ghép với La Phù → Nguyễn Trãi |
| 1141 | Lộ trình kế hoạch ghép (`S_0 → S_1 → S_2 → S_3`): |
| 1155 | Bước 1 — Tính giá xe đơn tham chiếu ($P_A, P_B$): |
| 1162 | Bước 2 — Tính `PlanFare` và Kiểm tra 2 cổng Mục 14: |
| 1178 | Bước 3 — Phân bổ giá theo trọng số bất tiện (Mục 15.2 – 15.4): |
| 1202 | Bảng tổng hợp kết quả Mục 16.1: |
| 1210 | So sánh với hai phương pháp chia giá đối chứng (Dùng cho Khảo sát S1 / Giả thuyết H4): |
| 1218 | 16.2. Kiểm chứng Kịch bản biên #1: Tác dụng của Cận dưới `Floor_i` và Điều kiện khả thi `(F2)` trong chuyến 4 khách chênh lệch lớn |
| 1244 | 16.3. Kiểm chứng Kịch bản biên #2: Chèn khách C khi khách B đã khóa giá (`pool_lock_point`) |
| 1264 | 17. THU NHẬP TÀI XẾ KHI GHÉP, QUY TẮC LÀM TRÒN VÀ ĐỐI SOÁT PHẦN LẺ |
| 1266 | 17.1. Biểu phí hoa hồng và đóng góp Quỹ bảo đảm |
| 1276 | 17.2. Quy tắc hạch toán hoa hồng trên Tổng tiền thực thu sau làm tròn (`[ACCEPTED]` — D-51 / O-05) |
| 1293 | 17.3. Bảng đối sánh thu nhập của tài xế (Ví dụ chuẩn Mục 16.1) |
| 1307 | 18. CƠ CHẾ CHIA SẺ RỦI RO BA BÊN KHI KHÔNG GHÉP ĐƯỢC, CHỐNG PHÁ GHÉP VÀ KHUNG CHÍNH SÁCH HỦY |
| 1309 | 18.1. Lý do loại bỏ mô hình phụ phí cố định +20% cũ |
| 1316 | 18.2. Năm nguyên tắc của cơ chế chia sẻ rủi ro ba bên (`[ACCEPTED]` — D-09 đến D-15) |
| 1336 | 18.3. Công thức tính `Quote_i`, `Gap_i`, `Unmatched_i` và Khoản bù bảo đảm |
| 1357 | 18.4. Ví dụ định lượng: Khách A đặt Taxi ghép nội đô nhưng không có khách ghép tương thích |
| 1378 | 18.5. Ma trận quy kết trách nhiệm theo nguyên nhân (`unmatched_cause`) |
| 1388 | 18.6. Cơ chế chống phá ghép: Nhận chuyến Pool là cam kết tự động nhận khách tương thích |
| 1396 | 18.7. Khung tham số Chính sách hủy chuyến và Khách không đến (`Cancellation & No-Show Policy` — `[ACCEPTED]` D-52) |
| 1414 | 19. QUỸ BẢO ĐẢM GHÉP: CÔNG THỨC HÒA VỐN TỔNG QUÁT VÀ PHÂN TÍCH ĐỘ NHẠY |
| 1416 | 19.1. Nguồn thu, Nguồn chi và Đơn vị thống kê chuẩn (`[ACCEPTED]` — D-19) |
| 1423 | 19.2. Công thức điều kiện hòa vốn tổng quát theo kỳ vọng quần thể (`p*_booking` vs `p*_ride`) |
| 1445 | Đối chiếu số học trên ví dụ chuẩn (Khách A = `194.000 đ`, Khách B = `133.000 đ`): |
| 1461 | 19.3. Phân tích độ nhạy và Đòn bẩy điều hành khi mật độ nhu cầu thấp |
| 1479 | 20. TRẢI NGHIỆM HIỂN THỊ GIÁ MINH BẠCH VÀ VÒNG ĐỜI GIÁ CỦA BOOKING POOL |
| 1481 | 20.1. Minh họa giao diện thẻ gợi ý Top-K cho Hành khách A |
| 1499 | 20.2. Quy tắc tính Giá ghép dự kiến (`Fare_matched_est`) cho hai loại ứng viên Pool (`[ACCEPTED]` — D-50b) |
| 1514 | 20.3. Vòng đời các trường giá trên bản ghi `Booking` |
| 1527 | 21. ĐỘNG CƠ KINH TẾ CỦA TÀI XẾ THAY CHO HẠN NGẠCH QUOTA 4:1 |
| 1543 | 22. MÁY TRẠNG THÁI CHI TIẾT CỦA TAXI GHÉP NỘI ĐÔ |
| 1566 | 23. ĐIỂM ĐÓN GẶP NHAU (MEETING POINTS — COULD C9) |
| 1568 | 23.1. Động cơ vận trù học |
| 1571 | 23.2. Thuật toán sinh điểm đón ứng viên |
| 1582 | 23.3. Bù đắp công sức đi bộ trong công thức giá và Quy tắc an toàn |
| 1588 | 24. CHUYẾN QUEN LẶP LẠI HẰNG NGÀY (RECURRING TRIPS — COULD C4) |
| 1597 | PHẦN IV — LIÊN TỈNH: TAXI BAO XE VÀ TAXI GHÉP THEO LỊCH TRÌNH |
| 1599 | 25. TAXI BAO XE LIÊN TỈNH (`CAR_INTERCITY_PRIVATE`) |
| 1601 | 25.1. Quy tắc đặt chuyến và Tìm nguồn cung |
| 1609 | 25.2. Công thức giá Taxi bao xe liên tỉnh |
| 1636 | 26. TAXI GHÉP LIÊN TỈNH (`CAR_INTERCITY_POOL`): TÀI XẾ ĐĂNG CHUYẾN VÀ QUẢN LÝ NGƯỠNG |
| 1661 | 27. CÁC MỐC THỜI GIAN VÒNG ĐỜI CHUYẾN GHÉP LIÊN TỈNH (`T−7 NGÀY` → `T`) |
| 1690 | 28. MÔ HÌNH GIÁ GHẾ SUY NGƯỢC TỪ NGƯỠNG KHỞI HÀNH VÀ CÔNG THỨC PHỤ PHÍ NGOÀI VÙNG (`DoorSurcharge`) |
| 1692 | 28.1. Công thức Giá ghế tham chiếu (`SeatReference`) (`[ACCEPTED]` — D-38) |
| 1711 | 28.2. Kiểm chứng định lượng trên tuyến Hà Đông → TP Hưng Yên (`65 km`) |
| 1730 | 28.3. Công thức tất định tính Phụ phí đón/trả ngoài vùng miễn phí (`DoorSurcharge` — `[ACCEPTED]` P1-02) |
| 1755 | 28.4. Tổng giá một Booking ghép liên tỉnh |
| 1765 | 29. QUY TRÌNH CHỐT CHUYẾN TẠI `T−72H`, GÓP THÊM TỰ NGUYỆN (`CONFIRMED_TOPUP`) VÀ XỬ LÝ THIẾU KHÁCH |
| 1811 | Quy tắc chuẩn hóa hoa hồng khi chuyển sang `CONFIRMED_TOPUP` (`[ACCEPTED]` — P0-04) |
| 1824 | 30. THUẬT TOÁN VÀ QUY TẮC GỘP CHUYẾN LIÊN TỈNH (`POOL_TRIP_MERGED` — SHOULD S5) |
| 1828 | 30.1. Điều kiện tương thích để gộp Chuyến nguồn $Y$ (bị gộp) vào Chuyến đích $X$ (nhận khách) |
| 1835 | 30.2. Quy tắc bảo vệ giá, Ký quỹ và Cửa sổ xác nhận gộp chuyến (`[ACCEPTED]` — P2-02) |
| 1852 | 31. TỐI ƯU HÓA THỨ TỰ ĐÓN TẠI `T−24H` |
| 1863 | 32. MÁY TRẠNG THÁI CHI TIẾT CỦA CHUYẾN GHÉP LIÊN TỈNH |
| 1888 | 33. CÁC MỞ RỘNG LIÊN TỈNH (COULD — C10, C11) |
| 1899 | PHẦN V — THUẬT TOÁN ĐỊNH TUYẾN, SINH ỨNG VIÊN, GHÉP XE VÀ KIỂM SOÁT ĐỒNG THỜI |
| 1901 | 34. ĐỊNH TUYẾN OSRM HAI PROFILE, KHÔNG GIAN POSTGIS VÀ CHIẾN LƯỢC GỌI MA TRẬN ĐƠN LẺ |
| 1916 | Quy tắc tối ưu hiệu năng: Một cuộc gọi ma trận OSRM duy nhất cho mỗi luồng sinh ứng viên (`[ACCEPTED]` — P2-04) |
| 1922 | 35. THUẬT TOÁN SINH ỨNG VIÊN CHO NĂM DỊCH VỤ VÀ QUY TẮC TRỘN TOP-K |
| 1924 | 35.1. Xe máy nội đô (`BIKE_URBAN`) và Taxi bao xe nội đô (`CAR_URBAN_PRIVATE`) |
| 1941 | 35.2. Taxi ghép nội đô (`CAR_URBAN_POOL`) |
| 1967 | 35.3. Taxi bao xe liên tỉnh (`CAR_INTERCITY_PRIVATE`) |
| 1980 | 35.4. Taxi ghép liên tỉnh (`CAR_INTERCITY_POOL`) |
| 1995 | 35.5. Quy tắc gộp và bảo toàn đa dạng trong Top-K (`[ACCEPTED]` — D-40) |
| 2004 | 36. THUẬT TOÁN CHÈN ĐIỂM ĐÓN/TRẢ ĐỘNG CÓ NHẬN BIẾT TRẠNG THÁI XE ĐANG CHẠY |
| 2079 | 37. THUẬT TOÁN GHÉP THEO LÔ (BATCH MATCHING CP-SAT TRÊN ĐỒ THỊ RTV RÚT GỌN — SHOULD S4) |
| 2081 | 37.1. Phạm vi áp dụng trong luồng đặt xe |
| 2086 | 37.2. Mô hình hóa chính xác bằng Đồ thị Yêu cầu – Chuyến khả thi – Phương tiện (RTV-Graph CP-SAT — `[ACCEPTED]` P1-08) |
| 2135 | 38. TỔNG HỢP THUẬT TOÁN ĐỊNH GIÁ TOÀN HỆ THỐNG |
| 2177 | 39. MÔ HÌNH XÁC SUẤT HOÀN THÀNH CHUYẾN (`p_fulfill`) THEO CÂY SỰ KIỆN TUẦN TỰ |
| 2183 | 39.1. Đối với các dịch vụ có bước gửi Offer (`BIKE_URBAN`, `CAR_URBAN_PRIVATE`, `CAR_URBAN_POOL`, `CAR_INTERCITY_PRIVATE`) |
| 2201 | 39.2. Đối với dịch vụ Taxi ghép liên tỉnh (`CAR_INTERCITY_POOL`) |
| 2216 | 39.3. Xử lý khởi đầu lạnh (Cold Start) cho tài xế mới |
| 2224 | 40. HÀM MỤC TIÊU GỢI Ý BASELINE CÓ GIẢI THÍCH |
| 2259 | 41. CHUỖI GỬI OFFER (OFFER CASCADE) VÀ CƠ CHẾ GIỮ GHẾ THEO TỪNG BƯỚC (`Per-Offer Seat Hold`) |
| 2263 | Khắc phục lỗi xung đột TTL giữa `seat_hold` và `offer_cascade` của Revision 8 (`[ACCEPTED]` — P0-05, D-47) |
| 2305 | 42. KIỂM SOÁT ĐỒNG THỜI BẰNG `plan_version`, KHÓA DÒNG VÀ TÍNH LŨY ĐẲNG (`Idempotency-Key`) |
| 2332 | PHẦN VI — TRÍ TUỆ NHÂN TẠO (AI/ML), SIMULATOR VÀ PHƯƠNG PHÁP NGHIÊN CỨU |
| 2334 | 43. VAI TRÒ, RANH GIỚI AN TOÀN VÀ CÁC BÀI TOÁN AI TRONG HỆ THỐNG |
| 2355 | Tổng hợp các mô hình AI/ML trong kiến trúc |
| 2369 | 44. MÔ HÌNH LEARNING-TO-RANK (LTR) XẾP HẠNG ĐA PHƯƠNG TIỆN VÀ THIẾT KẾ CHẨN ĐOÁN 2×2 |
| 2371 | 44.1. Định nghĩa Đơn vị truy vấn (Query Group), Ứng viên (Item) và Nhãn huấn luyện (Label) |
| 2376 | 44.2. Danh mục Đặc trưng đầu vào (Feature Schema — Chỉ dùng thông tin quan sát được tại thời điểm xếp hạng) |
| 2411 | 44.3. Báo cáo phân tách theo phân khúc (Segmented Evaluation) và Nâng `H9` lên MUST (`[ACCEPTED]` — P0-08) |
| 2418 | 44.4. Ma trận thực nghiệm Chẩn đoán 2×2 (2×2 Ablation Diagnostic — Giả thuyết H2) |
| 2429 | 45. MÔ HÌNH DỰ BÁO XÁC SUẤT GHÉP THÀNH CÔNG `P(MATCH)` VÀ QUY TRÌNH HUẤN LUYỆN OUT-OF-FOLD |
| 2431 | 45.1. Định nghĩa Bài toán và Nhãn quan sát |
| 2437 | 45.2. Đặc trưng đầu vào (Strictly Point-in-Time tại thời điểm báo giá $t_{\text{quote}}$) |
| 2454 | 45.3. Các mốc đối chứng (Baselines), Hiệu chỉnh và Quy trình Out-of-Fold chống rò rỉ (`[ACCEPTED]` — P1-07) |
| 2465 | 46. MÔ HÌNH HOÀN THÀNH CHUYẾN CÓ ĐIỀU KIỆN VÀ XỬ LÝ RỦI RO CẠNH TRANH (SHOULD S2) |
| 2475 | 47. HIỆU CHỈNH XÁC SUẤT (CALIBRATION) VÀ CÔNG THỨC ĐIỂM XẾP HẠNG CUỐI CÙNG |
| 2497 | 48. THIẾT KẾ SIMULATOR 5 DỊCH VỤ TÁI LẬP ĐƯỢC VÀ CƠ CHẾ CHỐNG RÒ RỈ BIẾN ẨN |
| 2501 | 48.1. Mô hình hành vi lựa chọn ẩn của Hành khách (Heterogeneous Non-Linear Passenger Utility) |
| 2521 | 48.2. Cơ chế mô phỏng mạng lưới Nội đô (3 dịch vụ) |
| 2527 | 48.3. Cơ chế mô phỏng mạng lưới Liên tỉnh (2 dịch vụ) |
| 2533 | 48.4. Cơ chế Tái lập kết quả (Deterministic Reproducibility) và Tường lửa Chống rò rỉ |
| 2539 | 49. XỬ LÝ KHỞI ĐẦU LẠNH (COLD START) VÀ THIÊN LỆCH VỊ TRÍ HIỂN THỊ (POSITION BIAS) |
| 2546 | 50. CHATBOT CHUYỂN ĐỔI NGÔN NGỮ TỰ NHIÊN THÀNH TRIP INTENT (COULD C1) |
| 2565 | 51. DỰ BÁO NHU CẦU TAXI GHÉP THEO KHU VỰC × 15 PHÚT (COULD C2) |
| 2574 | 52. MÔ HÌNH DỰ BÁO XÁC SUẤT ĐỦ GHẾ LIÊN TỈNH `P(FILL)` (COULD C10) |
| 2582 | PHẦN VII — KIẾN TRÚC PHẦN MỀM, CƠ SỞ DỮ LIỆU, API, BẢO MẬT, AN TOÀN VÀ PHÁP LÝ |
| 2584 | 53. NGĂN XẾP CÔNG NGHỆ (TECHNOLOGY STACK) |
| 2601 | 54. PHÂN RÃ MODULE VÀ RANH GIỚI GIAO TIẾP TRONG MODULAR MONOLITH |
| 2626 | 55. THIẾT KẾ BẢNG TÁC VỤ ĐỊNH THỜI (`scheduled_jobs`) VÀ CƠ CHẾ THỰC THI AN TOÀN |
| 2660 | 56. THIẾT KẾ CƠ SỞ DỮ LIỆU, RÀNG BUỘC TOÀN VẸN (CONSTRAINTS) VÀ CHỈ MỤC (INDEXES) |
| 2662 | 56.1. Cập nhật Schema các bảng cốt lõi trong Revision 9 |
| 2764 | 56.2. Ràng buộc toàn vẹn (Integrity Constraints) và Chỉ mục (Indexes) bắt buộc (`[ACCEPTED]` — P2-06) |
| 2793 | 57. ĐẶC TẢ GIAO DIỆN API VÀ QUY TẮC XỬ LÝ LỖI / ĐỒNG THỜI |
| 2796 | 1. Hành khách — Luồng chung & Đặt xe |
| 2807 | 2. Hành khách — Mở rộng Nội đô & Liên tỉnh |
| 2815 | 3. Tài xế |
| 2833 | 4. Quản trị viên (Admin) |
| 2842 | 5. Đồng bộ Blockchain |
| 2848 | 58. DANH MỤC SỰ KIỆN HỆ THỐNG (DOMAIN & AUDIT EVENTS) |
| 2851 | Sự kiện Nội đô & Ghép xe |
| 2863 | Sự kiện Liên tỉnh |
| 2872 | Sự kiện Ký quỹ Blockchain |
| 2882 | 59. KIẾN TRÚC BẢO MẬT, PHÂN QUYỀN VÀ BẢO VỆ DỮ LIỆU CÁ NHÂN (PRIVACY) |
| 2897 | 60. CƠ CHẾ AN TOÀN CHO HÀNH KHÁCH VÀ TÀI XẾ KHI ĐI GHÉP (SHOULD S9) |
| 2908 | 61. PHÂN TÍCH RỦI RO PHÁP LÝ TẠI VIỆT NAM VÀ GIẢI PHÁP HỢP ĐỒNG ĐIỆN TỬ ĐỒNG THUÊ CHUYẾN |
| 2912 | 61.1. Khung pháp lý hiện hành liên quan trực tiếp đến 5 dịch vụ của nền tảng |
| 2923 | 61.2. Định vị phạm vi đồ án và Giải pháp thiết kế tuân thủ khi chuyển giao thực tế |
| 2933 | 62. THIẾT KẾ GIAO DIỆN NGƯỜI DÙNG (UI SCREENS & UNIFIED DEMO WORKBENCH) |
| 2937 | 62.1. Phân hệ Hành khách (`PASSENGER VIEW`) |
| 2946 | 62.2. Phân hệ Tài xế (`DRIVER VIEW`) |
| 2954 | 62.3. Phân hệ Quản trị viên (`ADMIN VIEW`) |
| 2962 | 63. HỆ THỐNG CHỈ SỐ GIÁM SÁT VẬN HÀNH VÀ KỸ THUẬT (OBSERVABILITY METRICS) |
| 2965 | 1. Chỉ số Kỹ thuật & Độ trễ chung |
| 2975 | 2. Chỉ số chuyên biệt cho Taxi ghép nội đô (CAR_URBAN_POOL) |
| 2984 | 3. Chỉ số chuyên biệt cho Liên tỉnh (CAR_INTERCITY_PRIVATE & CAR_INTERCITY_POOL) |
| 2990 | 4. Chỉ số Đồng bộ Ký quỹ Blockchain |
| 2997 | PHẦN VIII — CHIẾN LƯỢC DỮ LIỆU, THIẾT KẾ KHẢO SÁT VÀ QUẢN LÝ TẬP HUẤN LUYỆN |
| 2999 | 64. CHIẾN LƯỢC NGUỒN DỮ LIỆU ĐA TẦNG |
| 3012 | 65. THIẾT KẾ KHẢO SÁT LỰA CHỌN RỜI RẠC (STATED PREFERENCE SURVEY — S1) VÀ PHÂN TẦNG MẪU |
| 3016 | 65.1. Quy mô và Phân tầng đối tượng khảo sát (Quota Sampling) |
| 3022 | 65.2. Cấu trúc bảng hỏi trực quan (Thời gian hoàn thành ~4–5 phút) |
| 3036 | 65.3. Phương pháp ước lượng tham số và Đánh giá chéo 5-Fold theo người trả lời (`GroupKFold CV`) |
| 3043 | 66. CẤU TRÚC BẢN GHI HUẤN LUYỆN (TRAINING INSTANCE SCHEMA) |
| 3080 | 67. QUY TẮC CHIA TẬP DỮ LIỆU THEO THỜI GIAN VÀ CHỐNG RÒ RỈ THÔNG TIN |
| 3102 | 68. QUY MÔ DỮ LIỆU THEO TỪNG CẤP ĐỘ KIỂM THỬ |
| 3117 | 69. QUẢN LÝ PHIÊN BẢN VÀ TRUY VẾT DỮ LIỆU – MÔ HÌNH (LINEAGE & REPRODUCIBILITY) |
| 3139 | PHẦN IX — KẾ HOẠCH KIỂM THỬ, GIẢ THUYẾT NGHIÊN CỨU VÀ DEFINITION OF DONE |
| 3141 | 70. HỆ THỐNG 18 CỔNG ĐÚNG ĐẮN BẮT BUỘC (`= 0` INVARIANT GATES) |
| 3171 | 71. ĐẶC TẢ KIỂM THỬ ĐỊNH GIÁ VÀ CÁC BẤT BIẾN TOÁN HỌC (PROPERTY-BASED TESTING SPEC) |
| 3173 | 71.1. Các ca kiểm thử hồi quy cố định (Fixed Regression Vectors) |
| 3190 | 71.2. Các bất biến kiểm thử tự động trên dữ liệu sinh ngẫu nhiên (Hypothesis Property-Based Invariants) |
| 3209 | 72. ĐẶC TẢ KIỂM THỬ LUẬT DỊCH VỤ, THỜI GIAN ĐẶT VÀ VÒNG ĐỜI LIÊN TỈNH |
| 3230 | 73. ĐẶC TẢ KIỂM THỬ ĐỒNG THỜI, STATE MACHINE VÀ BẢO MẬT |
| 3253 | 74. HỆ THỐNG GIẢ THUYẾT NGHIÊN CỨU (`H1–H11`) VÀ MA TRẬN ÁNH XẠ ĐÓNG GÓP |
| 3273 | 75. THIẾT KẾ PHƯƠNG PHÁP ĐÁNH GIÁ THỰC NGHIỆM VÀ KIỂM ĐỊNH THỐNG KÊ |
| 3301 | 76. HỆ THỐNG CHỈ SỐ ĐÁNH GIÁ TOÀN DIỆN (EVALUATION METRICS) |
| 3312 | 77. CHỈ TIÊU HIỆU NĂNG HỆ THỐNG (SLA / LATENCY TARGETS) |
| 3330 | 78. TIÊU CHUẨN HOÀN THÀNH DỰ ÁN (DEFINITION OF DONE — ĐẠT / TỐT / XUẤT SẮC) |
| 3332 | Mức ĐẠT (Hoàn thành 100% phạm vi MUST — Đủ điều kiện bảo vệ vững chắc) |
| 3350 | Mức TỐT (Hoàn thành MUST + SHOULD — Hướng tới điểm Giỏi / Xuất sắc) |
| 3356 | Mức XUẤT SẮC (Hoàn thành thêm các hạng mục COULD) |
| 3361 | PHẦN X — LỘ TRÌNH TRIỂN KHAI, TÍCH HỢP BLOCKCHAIN ESCROW VÀ QUẢN TRỊ RỦI RO |
| 3363 | 79. LỘ TRÌNH 12 PHASE THEO PHỤ THUỘC KỸ THUẬT VÀ THỨ TỰ CẮT GIẢM AN TOÀN |
| 3382 | Thứ tự cắt giảm an toàn nếu gặp áp lực tiến độ (`Graceful Scope Degradation`) |
| 3392 | 80. THIẾT KẾ KIẾN TRÚC KÝ QUỸ BLOCKCHAIN (ESCROW LIFECYCLE, ĐƠN VỊ TIỀN TỆ, QUỸ ON-CHAIN & XỬ LÝ LỖI) |
| 3396 | 80.1. Bốn nguyên tắc kiến trúc của lớp Ký quỹ Blockchain (`[ACCEPTED]` — D-33, D-34, D-48, D-49) |
| 3412 | 80.2. Bảng ánh xạ đầy đủ Vòng đời nghiệp vụ sang Giao dịch Hợp đồng thông minh |
| 3428 | 80.3. Đặc tả Quỹ bảo đảm nội bộ trên Hợp đồng thông minh (`onChainGuaranteeFundBalance` — `[ACCEPTED]` P1-05) |
| 3435 | 80.4. Cơ chế Đợi xác nhận, Thử lại (Retry) và Đối soát bất đồng bộ |
| 3442 | 81. QUY TRÌNH XÁC MINH TÀI XẾ KYC MOCK (SHOULD S7) |
| 3458 | 82. BẢNG QUẢN TRỊ RỦI RO KỸ THUẬT, NGHIÊN CỨU VÀ VẬN HÀNH |
| 3474 | 83. TỔNG KẾT THIẾT KẾ REVISION 9 |
| 3483 | 84. HƯỚNG PHÁT TRIỂN SAU ĐỒ ÁN |
| 3492 | PHỤ LỤC A — DECISION REGISTER CẬP NHẬT (`D-01` ĐẾN `D-52`) |
| 3554 | PHỤ LỤC B — BẢNG THAM SỐ CẤU HÌNH CHUẨN (YAML SPECIFICATION) |
| 3689 | PHỤ LỤC C — TỪ ĐIỂN THUẬT NGỮ VÀ KÝ HIỆU TOÁN HỌC |
| 3713 | PHỤ LỤC D — TÀI LIỆU THAM KHẢO HỌC THUẬT VÀ PHÁP LÝ |
| 3715 | A. Tài liệu học thuật quốc tế (Optimization, Game Theory & Machine Learning) |
| 3730 | B. Văn bản quy phạm pháp luật Việt Nam (Tham chiếu tại Mục 61) |
| 3738 | PHỤ LỤC E — HỒ SƠ PHÂN TÍCH CÁC QUYẾT ĐỊNH MỞ VÀ ĐÁNH ĐỔI THIẾT KẾ (`O-01` ĐẾN `O-08`) |
| 3744 | O-01: Chọn ngưỡng cận dưới (`Floor_i`) và hàm trọng số trong phân bổ giá ghép nội đô (Mục 15.3 — `D-43`) |
| 3759 | O-02: Xử lý xung đột giữa Chèn khách động khi xe đang chạy và Giá của hành khách đã qua `pool_lock_point` (Mục 15.5 — `D-44`) |
| 3773 | O-03: Xử lý Bất biến tốc độ thu nhập theo giờ của tài xế khi ghép (`DriverHourlyRate` — Mục 14.2 & 17 — `D-45a`) |
| 3786 | O-04: Hệ số phụ trội ghế thứ hai ($\gamma_{\text{seat}}$) cho Booking đặt 2 khách trong `CAR_URBAN_POOL` (Mục 12.2 & 15.2 — `D-45b`) |
| 3800 | O-05: Hạch toán phần lẻ làm tròn xuống `1.000 đ` và Đơn vị cơ sở trên Smart Contract (Mục 17.2 & 80.1 — `D-48, D-51`) |
| 3810 | O-06: Cổng kiểm tra ký quỹ trước `RIDE_STARTED` và Mô hình ví ở phạm vi MUST (Mục 9.3 & 80.1 — `D-34, D-49`) |
| 3819 | O-07: Lựa chọn tên đề tài chính thức và Phân tầng mẫu Khảo sát S1 (Mục 0.1 & 65 — `D-30`) |
| 3828 | O-08: Cho phép hay đóng cứng việc đặt ghế vét trên chuyến ghép liên tỉnh đã `CONFIRMED` trong khoảng `[T−72h, T−24h]` (Mục 2.2 & 27) |

## mvp_config_baseline_v1.md

353 dòng; 37904 bytes; SHA-256 `766b08864448d9efd5da6c70fbe8f4ef1622e10ff98ebae15a7a361dad382e66`.

| Dòng | Nội dung |
|---:|---|
| 1 | BỘ CẤU HÌNH BASELINE ĐÓNG BĂNG CHO MVP — REVISION 9 (`MVP_CONFIG_BASELINE_V1.md`) |
| 15 | 1. MỤC ĐÍCH VÀ NGUYÊN TẮC QUẢN TRỊ CẤU HÌNH (`CONFIGURATION GOVERNANCE`) |
| 26 | 2. TÓM TẮT 4 HIỆU CHỈNH ĐỒNG BỘ ĐÃ KHÓA TRONG CẤU HÌNH (`LOCKED MATHEMATICAL RULES`) |
| 28 | 2.1. Quy tắc `party_seat_surcharge_gamma` ($\gamma_{\text{seat}} = 0.35$), `Quote_i`, `Gap_i`, `Unmatched_i` cho Booking 2 ghế (`D-45b` / `O-04` — `ACCEPTED`) |
| 40 | 2.2. Điều kiện khả thi cần và đủ của Thuật toán phân bổ hai cận và Xử lý khi vô nghiệm (`D-43` / `O-01` — `ACCEPTED`) |
| 50 | 2.3. Hệ 6 điều kiện đầy đủ (`D1–D6`) khi chèn khách mới lúc giá cũ đã khóa (`D-44` / `O-02` — `ACCEPTED`) |
| 59 | 2.4. Đồng bộ cơ sở tính Thu nhập/giờ của tài xế theo Khoản Payout thực tế sau làm tròn (`D-45a` / `D-51` — `ACCEPTED`) |
| 66 | 3. BẢNG ĐẶC TẢ CHI TIẾT CÁC THAM SỐ BASELINE (`PARAMETER SPECIFICATION TABLES`) |
| 68 | 3.1. Nhóm Không gian, Vùng phục vụ & Định tuyến (`spatial_and_service_areas`) |
| 76 | 3.2. Nhóm Dịch vụ Xe máy Nội đô (`bike_urban` — `BIKE_URBAN`) |
| 89 | 3.3. Nhóm Dịch vụ Taxi Nội đô Bao xe & Ghép (`car_urban` — `CAR_URBAN_PRIVATE` & `CAR_URBAN_POOL`) |
| 119 | 3.4. Nhóm Dịch vụ Liên tỉnh (`car_intercity_private` & `car_intercity_pool`) |
| 144 | 3.5. Nhóm Đặt xe, Đồng thời, Ký quỹ Blockchain & Chính sách Phí hủy (`booking_and_concurrency` & `cancellation_policy`) |
| 164 | 3.6. Nhóm Tối ưu hóa mở rộng, AI/ML & Simulator (`batch_matching`, `meeting_points`, `simulator_and_evaluation`) |
| 180 | 4. KHỐI CẤU HÌNH YAML CHUẨN ĐÓNG BĂNG (`mvp_config_baseline_v1.yaml`) |
| 320 | 5. QUY TẮC THAY ĐỔI PHIÊN BẢN VÀ CÔ LẬP SNAPSHOT (`VERSIONING & SNAPSHOT ISOLATION RULES`) |
| 333 | 6. PHÂN LOẠI 3 NHÓM VẤN ĐỀ CÒN LẠI VÀ KẾT LUẬN TRẠNG THÁI SẴN SÀNG (`READINESS GATE VERDICT`) |
| 335 | 6.1. Bảng phân loại 3 nhóm vấn đề sau khi Chủ dự án đã phê duyệt cấu hình Baseline v1 |
| 347 | 6.2. Kết luận Trạng thái Sẵn sàng Chính thức (`FINAL READINESS VERDICT`) |

## revision_9_decision_register.md

83 dòng; 18611 bytes; SHA-256 `c2b20f041bcaf6fdf9c6f39814c5f915e25556749cfc1693b66102617d541807`.

| Dòng | Nội dung |
|---:|---|
| 1 | SỔ ĐĂNG KÝ QUYẾT ĐỊNH THIẾT KẾ — REVISION 9 (`REVISION_9_DECISION_REGISTER.md`) |
| 8 | Quy ước Nhãn trạng thái Quyết định (Decision Status Taxonomy) |
| 17 | 1. BẢNG TỔNG HỢP TOÀN BỘ QUYẾT ĐỊNH THIẾT KẾ (`D-01` ĐẾN `D-52`) |
| 19 | Nhóm I — Các quyết định nền tảng được bảo toàn từ Revision 5–8 (`ACCEPTED`) |
| 58 | Nhóm II — Các quyết định được sửa đổi, nâng cấp và phê duyệt khóa trong Revision 9 (`D-06`, `D-20`, `D-21`, `D-29`, `D-30`, `D-34`, `D-36`, `D-38..D-40`, `D-43..D-52`) |

## revision_8_to_revision_9_changelog.md

65 dòng; 23421 bytes; SHA-256 `f5fb1e56821c568a936db5867ddd8b64052831136eda158f993d15d8a7d77722`.

| Dòng | Nội dung |
|---:|---|
| 1 | NHẬT KÝ THAY ĐỔI CHI TIẾT: TỪ REVISION 8 SANG REVISION 9 & KHÓA CẤU HÌNH BASELINE (`REVISION_8_TO_REVISION_9_CHANGELOG.md`) |
| 10 | 1. XÁC MINH HIỆN TRẠNG CẤU TRÚC CỦA FILE REVISION 8 (MỤC 3.3) |
| 18 | 2. BẢNG ĐỐI CHIẾU XỬ LÝ TỪNG PHÁT HIỆN P0 VÀ P1 TRONG REVISION 9 |
| 42 | 3. TỔNG HỢP CÁC CẢI TIẾN P2 VÀ P3 ĐÃ TÍCH HỢP VÀO REVISION 9 |
| 56 | 4. NHẬT KÝ HIỆU CHỈNH ĐỒNG BỘ & PHÊ DUYỆT KHÓA CẤU HÌNH BASELINE (`FINAL CONFIGURATION FREEZE — V1`) |
