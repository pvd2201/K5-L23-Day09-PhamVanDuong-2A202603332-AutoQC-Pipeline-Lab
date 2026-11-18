# Báo cáo Day 09 — Pham Van Duong, 2A202603332

> Số liệu lấy từ `submission/reports/`, calibration và kết quả chạy pipeline.

## 1. Kết luận trước
**Hold**. Pipeline quét 224 ảnh; 31 ảnh bị loại ở intake, còn 193 ảnh xử lý và xuất bản nháp 193 nhãn tại `submission/export/clean_v1/`. Sau sửa tự động còn 6 ảnh thiếu file nhãn bắt buộc, nhưng mô phỏng người duyệt đã xử lý chúng; vẫn còn 34/193 ảnh (17.62%) có cảnh báo chưa duyệt nên đạt ngưỡng Hold 10%, không phải Release.

## 2. Lỗi và phân việc
| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `POSSIBLE_MISSING` | 52 ảnh | người | Model phát hiện vật chưa có nhãn; máy không được bịa nhãn. |
| `POSSIBLE_FALSE_POS` | 26 ảnh | người | Box nhãn không khớp dự đoán model; cần nhìn ảnh. |
| `POSSIBLE_LOOSE_BOX` | 23 ảnh | người | Box có thể lệch nhẹ hoặc sai vật; máy không sửa ngữ nghĩa. |
| `POSSIBLE_WRONG_CLASS` | 17 ảnh | người | Model và nhãn trái lớp; cần xác nhận đúng lớp. |
| `EMPTY_LABEL` | 11 ảnh | người | File rỗng có thể là ảnh nền hoặc thiếu nhãn. |
| `LEAK_TEST` | 11 ảnh | máy | Loại khỏi bộ train vì trùng ảnh trong kho test/val. |
| `BOX_OUT_OF_IMAGE` | 8 dòng | máy | Cắt box hoặc bỏ dòng nếu box mất diện tích. |
| `DUP_IMAGE_EXACT` | 8 ảnh | máy | Trùng từng byte nên loại ảnh trùng. |
| `DUP_BOX` | 7 dòng | máy | Bỏ dòng trùng trong file nhãn. |
| `DUP_IMAGE_NEAR` | 7 ảnh | máy | Trùng gần đúng theo pHash với ngưỡng đã calibrate. |
| `BAD_CLASS_ID` | 6 dòng | máy | ID ngoài 0–3 bị loại an toàn. |
| `MISSING_LABEL_FILE` | 6 ảnh | người | Không tạo file rỗng; ảnh được ưu tiên lên hàng đợi. |
| `BOX_TINY` / `BOX_HUGE` | 4 / 3 ảnh | người | Cảnh báo kích thước; máy chỉ ghi cảnh báo. |
| `BOX_ZERO` | 4 dòng | máy | Cạnh không dương làm box vô hiệu. |
| `BAD_FORMAT` | 3 dòng | máy | Dòng không đủ 5 cột/số hợp lệ bị xoá. |
| `BAD_SIZE` | 3 ảnh | máy | Cạnh ngắn dưới 250 px bị loại ở intake. |
| `CORRUPT_IMAGE` | 2 ảnh | máy | Ảnh không mở được hoặc hỏng. |
| `BAD_CLASS_NAME` | 1 dataset | máy | Ghi lại `names` thành `car, person, truck, bus`. |
| `CLASS_RARE` | 1 thống kê cấp dataset | người | Lớp hiếm cần xem phân bố, không suy ra nhãn sai. |

Hàng đợi ưu tiên 6 ảnh `NEEDS_LABEL` với trọng số 10.0, sau đó là ảnh chồng nhiều cảnh báo hoặc fix quan trọng, ví dụ `img_0020` có điểm 11.524. Ngân sách là 80/121 ảnh cần người xem; 80 ảnh đầu hàng đã được mô phỏng duyệt và 41 ảnh còn lại chưa được duyệt.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 16 | DUP_IMAGE_NEAR: 1.00/0.50 → 1.00/0.83 | Tăng recall gần trùng từ 50% lên 83% mà vẫn giữ precision 1.00; ngưỡng 20 giảm exact recall. |
| `second_opinion.conf` | 0.25 | 0.60 | WRONG_CLASS: 0.56/0.83 → 0.62/0.83; MISSING: 0.50/1.00 → 0.57/1.00 | Giữ recall missing 100%, tăng precision wrong-class và missing; tránh hạ ngưỡng quá thấp làm nhiều cảnh báo giả. |

Điểm calibration dễ đánh lừa: bộ calib chỉ có 39 ảnh. Ngưỡng pHash 16 bắt 5/6 near-duplicate trong calib, nhưng trên raw có thể coi ảnh khác nhau là trùng nếu cảnh đổi trộn hoặc nền giống; trong kết quả intake có 31 ảnh bị loại và cần mở xem mẫu trước phát hành. Ngưỡng model 0.60 giảm FP ở calib nhưng vẫn có false-positive cảnh báo do model lớn hơn chưa chắc là đúng.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
Gate đã được chứng minh bằng:
`python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`.
Không có người duyệt nên 6 ảnh `MISSING_LABEL_FILE` còn nguyên; kết luận **Rework**, mã thoát 20 và pipeline không xuất dataset tại `work/exp_nb`.

Hai điểm pipeline không bắt chắc:
1. Box lỏng nhẹ hoặc sai khác mức mà model cũng có thể nhầm; calibration cho thấy `POSSIBLE_LOOSE_BOX` recall/thống kê còn thấp.
2. Nhầm lớp, vật che khuất hoặc ảnh trùng biến đổi mạnh có thể vượt quy tắc máy; model checker chỉ là ý kiến thứ hai, không thay thế người duyệt.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
**Chưa chạy** trên Colab/GPU, nên chưa có kết quả train raw vs clean để kết luận.

## 6. Quyết định và ghi chú AI
Quyết định cuối là **Hold**. Để chuyển Release, cần người duyệt 41 ảnh cảnh báo còn lại, đặc biệt 6 ảnh thiếu nhãn, xác nhận các cặp ảnh trùng và điểm nhầm lớp; sau đó cảnh báo chưa duyệt phải xuống dưới 10%.

**Dùng AI:** prompt chính yêu cầu implement đúng docstring và 4 module theo test. Kiểm tra bằng chạy từng test module, toàn bộ `pytest`, pipeline thật và trường hợp budget 0. Một lần AI sai là bản autofix đầu tiên có thể dịch sai dòng gốc khi vừa xoá rồi mới cắt box; đã sửa bằng xử lý drop/clip theo số dòng gốc giảm dần và chạy lại test.
