# Khảo sát S1 và đánh giá trên người thật

Ứng dụng có form công khai tại `/survey`, tám tình huống lựa chọn dịch vụ và ba bảng chia tiền cần chấm mức công bằng. **Chưa có dữ liệu người thật trong bản bàn giao; H4 chưa có kết luận.** Không dùng phản hồi sinh tự động để đủ quota.

## Công cụ và quyền riêng tư

- Người tham gia đồng ý trước khi gửi; không cần tài khoản.
- Mỗi trình duyệt giữ một UUID ngẫu nhiên để hạn chế trùng; không thu tên, email, số điện thoại hay tọa độ. Form gửi với `credentials: omit` và không gắn tài khoản đặt xe.
- Tám tình huống bắt buộc trả lời đúng một lần, có lựa chọn outside. API kiểm tra dịch vụ được phép trong từng tình huống, không nhận đặc trưng tùy ý từ client.
- Thứ tự trình bày ba phương pháp chia tiền được đảo theo UUID để giảm sai lệch do thứ tự. Bảng so sánh sử dụng giá chính xác trước làm tròn, được phân biệt với tiền thực thu khi đi xe.
- UUID vẫn có thể bị tạo lại nếu xóa bộ nhớ trình duyệt; nguyên mẫu không chứng minh được tính duy nhất của con người. Không bổ sung fingerprint hoặc định danh nhạy cảm để khắc phục điều này.

Đích thu thập: 100–200 người thật, tỷ lệ sinh viên/người đi làm trong khoảng 40–60%. `survey_quality` chỉ chuyển sang READY khi có ít nhất 100 UUID hợp lệ, không trùng và đạt quota. Cổng số lượng không tự xác nhận được nguồn gốc hay chất lượng người trả lời; người tổ chức phải ghi quy trình tuyển mẫu, đồng ý tham gia và điều kiện khảo sát riêng.

## Xuất và phân tích

```powershell
# Chạy bởi operator trong workspace, ghi file mới:
.venv\Scripts\python.exe -m app.export surveys --output data/private-survey/responses-v1.json
.venv\Scripts\python.exe -m research survey --responses data/private-survey/responses-v1.json --output artifacts/research/survey-report-v1.json
```

Phân tích H4 sử dụng Friedman cho ba mức chấm lặp lại trên cùng người, Wilcoxon cặp với hiệu chỉnh Bonferroni. Nếu chưa đủ mẫu/quota, `supported=null`, không biến một kết quả thăm dò thành nghiệm thu. Đánh giá lựa chọn dùng GroupKFold năm fold theo người tham gia; toàn bộ query của một người ở cùng fold, không chia ngẫu nhiên từng dòng ứng viên.

Mỗi fold so sánh Baseline và đối chứng 2×2: conditional logit/LambdaMART, raw/interactions. H1 và H2 dùng chênh lệch HR@1 trung bình theo từng người; H9 kiểm tra chênh lệch uplift giữa nội đô đa dịch vụ và các tình huống khác của cùng người. Bootstrap/permutation lấy người làm đơn vị độc lập thay vì coi tám câu trả lời của họ là tám người khác nhau. Không fit xác suất accepted/started/completed từ survey.

Survey không chứa outcome chuyến thật: không dùng một lựa chọn trên tình huống giả định để tạo nhãn accepted/started/completed. Các xác suất vận hành phải học từ log quan sát hợp lệ hoặc mô phỏng được gắn nhãn rõ ràng. Kết quả trên khảo sát và mô phỏng phải báo cáo tách biệt.
