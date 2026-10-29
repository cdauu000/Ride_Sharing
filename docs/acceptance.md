# Kịch bản nghiệm thu local

Chạy bootstrap và hai ứng dụng theo README. Tất cả số tiền dưới đây tính bằng VND; các quãng đường trong ví dụ local là fixture minh họa.

## Xe máy và bao xe

- `passenger@rise.local`: tìm Phenikaa → Đống Đa, chọn Xe máy.
- `bike@rise.local`: nhận offer trước 20s. Trước khi worker xác nhận tiền, bắt đầu chuyến phải bị từ chối.
- Khi ký quỹ xác nhận: bắt đầu, xác nhận điểm đón, điểm trả, đóng hành trình.
- Giá 81.000, tài xế 64.800, nền tảng 16.200; local tx_hash phải null.
- Dịch vụ private nội đô không nhận booking khác vào cùng xe. Liên tỉnh NOW dùng 65 km → 637.000, tài xế 541.450.

## Pool A+B và giá khóa

- A đặt Phenikaa → Đống Đa. Driver taxi nhận booking khởi tạo.
- B đặt La Phù → Nguyễn Trãi trong cửa sổ còn khả thi. Chọn ứng viên existing-plan; không tạo offer lần hai.
- Driver đi đúng chuỗi đón A, đón B, trả B, trả A. MATCHED chỉ xuất hiện sau đoạn đường thực có hai booking cùng trên xe.
- A thu 143.000, B thu 105.000; tài xế 210.800; nền tảng 29.760; Quỹ tăng 7.440.
- Vector chèn C sau khi B khóa: B giữ 105.000, A giảm 135.000, C 48.000 trong fixture toán ở `tests/test_pricing.py`. Không coi vector toán này là phép đo OSRM thực tế.

## Không ghép và phá ghép

- Một booking Pool hai ghế chạy riêng vẫn UNMATCHED. A thu 174.000; từ khách tài xế nhận 147.900, Quỹ bù 7.300.
- Tài xế từ chối khách ghép tương thích: khách searching còn lại chỉ trả Quote, cắt guarantee. Một giá đã khóa không được tăng; lỗi tài xế không được biến thành late-cancellation guarantee.
- Hủy booking HELD phải giải phóng hold/offer và không tạo ký quỹ.

## Liên tỉnh

- Tài xế đã VERIFIED và bật intercity đăng chuyến trước bốn ngày; giá tham chiếu 200.000/ghế cho fixture 65 km.
- Đủ ba ghế tại T−72h → CONFIRMED. Hủy một khách tại T−36h phạt 50%, chuyến còn lại tiếp tục chạy.
- Thiếu ghế: thử gộp phù hợp, bảo vệ giá giảm/giữ và cửa sổ hủy miễn phí hai giờ.
- Nếu góp thêm: tất cả booking phải ACCEPT trước khi gửi nạp thêm. Hai ghế: 318.000/ghế, hoa hồng 15%.
- Nếu DECLINE/hết hạn: tài xế quyết định RUN/CANCEL trước T−60h. Không phản hồi → hoàn 100%.
- Nếu một topup bị từ chối xác định sau khi khách khác đã nạp: hoàn phần tăng thêm và phục hồi mức giá ghế cũ trước RUN. Nếu RPC chưa rõ kết quả: giữ khóa RUN, thử lại đúng operation cũ và đối soát; không tự bỏ qua giao dịch.
- T−24h tối ưu thứ tự đón/trả; chỉ khởi hành từ chuyến đã chốt thứ tự và đủ ký quỹ.
- Yêu cầu còn 71h59m không có Pool liên tỉnh, vẫn có private nếu còn cung hợp lệ.

## Khả năng phục hồi và an toàn

- Gửi lại cùng key/payload → cùng booking; khác payload → 422.
- 20 luồng tranh ghế cuối → đúng một thành công, không oversell.
- Offer #1 hết hạn 20s, #2 hết hạn 40s, #3 nhận ở khoảng 59s → thành công nhờ hold riêng.
- Nhiều lệnh ký quỹ trùng timestamp vẫn giữ sequence; giả lập crash rồi retry không nhân tiền.
- No-show cần vị trí tài xế tại điểm đón và chờ đủ năm phút tính từ thời điểm hợp lệ trong cửa sổ đón.
- Người dùng khác không xem booking/tracking; share-token không trả điểm đón/trả hay người đồng hành; webhook giả bị từ chối.
- SOS chỉ ghi cảnh báo mô phỏng; người thử nghiệm phải thấy rõ điều này.

## Nghiên cứu

- Chạy lại cùng seed/config tạo cùng hash quan sát.
- Export không có theta, utility thật, tọa độ chính xác hoặc nhãn hậu nghiệm trong features.
- Query không bị tách qua Train/Validation/Test; outcome chưa có ở thời điểm cut bị embargo.
- OOF fold không được fit nhãn của held-out query; báo cáo 2×2, tách phân khúc và CI95%.
- Không tuyên bố H1/H2/H3/H9 được ủng hộ nếu CI/p-value không đủ, hoặc H4 đã hoàn tất khi chưa có khảo sát thật.
