# Nghiên cứu, kết quả và giới hạn suy luận

Ngày tổng hợp: 28/10/2026. Các kết quả hiện có là **dữ liệu tổng hợp, routing fixture**, chưa được hiệu chỉnh bằng khảo sát người thật. Việc có mô hình chạy được khác với việc một giả thuyết khoa học được ủng hộ.

## Thiết kế có thể tái lập

Simulator sử dụng cùng engine chèn và định giá với ứng dụng. Nhãn ghép xuất phát từ đoạn hành trình thực có hai booking cùng trên xe trong mô phỏng; hai ghế trong cùng booking không tạo nhãn MATCHED. Mỗi seed tái lập luồng yêu cầu và hành vi. Các chính sách trong so sánh kín dùng cùng luồng ngoại sinh, kiểm tra bằng SHA-256.

Quan sát xuất qua allowlist; sở thích ẩn, utility thật, tọa độ chính xác và thông tin hậu nghiệm không được đưa vào features. Regret sử dụng utility ẩn chỉ ở bộ đánh giá và chỉ xuất dạng tổng hợp. Export từ API để nhãn chưa quan sát là null, không gán một booking chưa kết thúc thành thất bại.

Chia dữ liệu theo thời gian ở mức toàn bộ query: 65% Train, 15% Validation, 20% Test; cùng timestamp ở cùng tập. Các outcome chưa tồn tại tại thời điểm cắt bị embargo. P(match) và P(fulfill) dùng đặc trưng OOF theo năm khối query; các cổng P(accepted), P(started|accepted), P(completed|started) học riêng theo mẫu đủ điều kiện. LTR học trên đặc trưng cross-fitted; lúc dự đoán dùng mô hình đã fit trên Train.

Validation được chia tiếp theo query/thời gian: phần sớm để fit isotonic/temperature; phần muộn để đo ECE và quyết định bật phép nhân. Test không dùng để fit hoặc chọn temperature. Pipeline lưu phiên bản, thư viện, hash artifact, provenance fold và hash mã Python ở những lần chạy mới. Workspace chưa có lịch sử Git; manifest ghi rõ `UNCOMMITTED_WORKSPACE`. Hash mã giúp kiểm tra phiên bản nhưng không tự thay thế bản sao mã nguồn tương ứng.

## Dataset chính đã chạy

Artifact: [manifest](../artifacts/research/main_v1/manifest.json), [metrics](../artifacts/research/main_v1/metrics.json), dữ liệu `artifacts/research/main_v1/observations.jsonl` và `.parquet`.

| Thuộc tính | Giá trị |
|---|---:|
| Seed / thời gian mô phỏng | 1000 / 28 ngày |
| Urban / intercity density | HIGH / HIGH |
| Yêu cầu | 50.000 |
| Dòng quan sát ứng viên | 166.487 |
| Yêu cầu có cung khả thi | 43.160 (86,32%) |
| Booking được chọn / hoàn thành | 39.916 / 38.081 |
| Pool hoàn thành / ghép thực tế | 5.223 / 3.408 |
| Tỷ lệ ghép theo booking Pool hoàn thành | 65,2499% |
| Quỹ đầu / cuối | 5.000.000 / 3.487.030 VND |
| Thu Quỹ / chi bảo đảm | 9.053.880 / 10.566.850 VND |

SHA-256 JSONL: `585ca30b3da1f2309efe5258e263fa4fd796b22c39a535fcfcbbaa4ff5989470`.

Quỹ giảm **1.512.970 VND** trong lần chạy này. Không thể suy ra hòa vốn chỉ từ tỷ lệ ghép 65,25% và ngưỡng minh họa của vector A/B: chi phí bảo đảm và đóng góp trong quần thể hiện tại khác vector chuẩn. Cần tính kỳ vọng thu/chi trên cùng quần thể, nhiều seed, mật độ và điều kiện thời tiết, đồng thời kiểm tra thanh khoản theo thời gian. Không thay thông số baseline đã khóa để làm kết quả dương.

## Đánh giá mô hình chính

Artifact: [manifest model](../artifacts/models/main_v1/manifest.json), [báo cáo offline](../artifacts/models/main_v1/offline_report.json), phiên bản `ltr_v9_main_v1`.

Train: 28.054 query; Validation: 6.474 query. Test có 8.632 query, trong đó 592 chọn outside. Chỉ số HR/MRR/NDCG và so sánh cặp dưới đây sử dụng **8.040 query có lựa chọn trong menu**; chúng không phải tỷ lệ chuyển đổi trên toàn bộ 50.000 yêu cầu.

| Mô hình | HR@1 | HR@3 | MRR | NDCG@5 |
|---|---:|---:|---:|---:|
| Baseline | 0,41667 | 0,79963 | 0,63429 | 0,70178 |
| Linear raw | 0,44577 | 0,87164 | 0,66927 | 0,74536 |
| Tree raw | 0,44701 | 0,87438 | 0,67122 | 0,74738 |
| Linear + interactions | 0,45597 | 0,87761 | 0,67678 | 0,75165 |
| Tree + interactions | 0,44975 | 0,87736 | 0,67428 | 0,74978 |

- **H1:** LTR full cải thiện HR@1 thêm 0,03308 và NDCG@5 thêm 0,04800 so với Baseline. CI95% NDCG delta [0,04306; 0,05322], permutation p≈0,001. Có bằng chứng trên dataset tổng hợp này.
- **H2:** chưa có bằng chứng cây vượt tuyến tính ở cùng bộ đặc trưng. Với full features, HR@1 của cây thấp hơn 0,00622; NDCG delta −0,00187 có CI chứa 0. Giữ mô hình tuyến tính có tương tác làm đối chứng nghiêm túc; không kết luận phi tuyến luôn tốt hơn.
- **H3 offline:** 977 quan sát Pool đủ nhãn; Brier model 0,15045 so với baseline không gian/thời gian 0,16309, delta cải thiện có CI95% [0,00230; 0,02291]. ECE Test vẫn 0,10836: khả năng phân biệt tốt hơn không có nghĩa hiệu chỉnh đủ tốt hay Quỹ được cải thiện.
- **H9:** chênh lệch uplift HR@1 giữa các phân khúc theo phép thử đã định nghĩa là −0,03856, CI95% [−0,05610; −0,02067]; `supported=false`. Không sửa giả thuyết sau khi thấy kết quả.

ECE selection ở phần Validation dùng kiểm định độc lập là 0,02717; ECE match là 0,06376. Hai cổng fulfillment sau thiếu nhãn đủ để đo ECE. Do đó `fulfillment_multiplication_enabled=false`: hệ thống giữ điểm LTR, chưa nhân các xác suất hoàn tất. Trạng thái `VALIDATION_FITTED` chỉ cho biết đã fit calibration, không có nghĩa mọi tiêu chuẩn chất lượng đã đạt.

## Đánh giá vòng kín

Hai mức bằng chứng được giữ riêng:

1. [closed_loop_v1](../artifacts/research/closed_loop_v1.json): 20 seed × 18 ô mật độ/thời tiết × 6 chính sách = 2.160 lần chạy, mỗi lần 100 yêu cầu/7 ngày. Dùng model smoke và logic cổng calibration phiên bản sớm; đây là artifact lịch sử để kiểm tra ma trận và tái lập, không dùng làm kết luận cho model chính.
2. [closed_loop_main_verification_v1](../artifacts/research/closed_loop_main_verification_v1.json): model chính, 20 seed × 1 ô HIGH/HIGH/mưa 0,1 × 5 chính sách, mỗi lần 100 yêu cầu/7 ngày. Cổng fulfillment không đạt nên không chạy chính sách nhân xác suất. Đây là smoke vòng kín với model hiện tại.

Ở smoke model chính: regret trung bình giảm từ 0,38471 xuống 0,19619 (delta −0,18853; CI95% [−0,24758; −0,14027]). Cơ chế cứu chuyến giảm tỷ lệ hủy liên tỉnh do thiếu khách từ 0,72241 xuống 0,54667. H3 và H6 vòng kín chưa có bằng chứng cải thiện đủ ở mẫu nhỏ này; H5 bị tắt bởi cổng chất lượng. Không ngoại suy các mức cải thiện sang vận hành thật.

**Chưa hoàn tất main benchmark đa seed, đủ 18 ô và 50.000 yêu cầu mỗi lần.** Cả hai báo cáo vòng kín ghi `main_benchmark_ready=false`. Mật độ luồng đến còn phụ thuộc số yêu cầu/thời gian mô phỏng; không gộp số đo từ smoke 100 yêu cầu với main 50.000 yêu cầu thành một quần thể.

## Chạy lại và mở rộng

```powershell
.venv\Scripts\python.exe -m research simulate --seed 1000 --requests 50000 --days 28 --density HIGH --intercity-density HIGH --output artifacts/research/main_new_version
.venv\Scripts\python.exe -m research train --dataset artifacts/research/main_new_version/observations.jsonl --output artifacts/models/main_new_version --version ltr_v9_new_version
.venv\Scripts\python.exe -m research closed-loop --model artifacts/models/main_new_version --requests 50000 --days 28 --seeds 1000:1019 --output artifacts/research/closed_loop_new_version.json
```

Lệnh cuối chạy toàn ma trận, cần tài nguyên và thời gian lớn; ghi lại cấu hình máy và giữ mã nguồn tương ứng. Chọn tên phiên bản mới: CLI từ chối ghi đè báo cáo/model bất biến. Khảo sát người thật và kiểm định OSRM cần hoàn tất trước khi kết luận tính phù hợp ngoài mô phỏng.

Tài liệu kỹ thuật tham chiếu: [LightGBM LGBMRanker](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRanker.html), [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html), [GroupKFold](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html).
