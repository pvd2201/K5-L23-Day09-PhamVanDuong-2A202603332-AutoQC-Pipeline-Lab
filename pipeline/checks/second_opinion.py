"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    sc = cfg["second_opinion"]
    issues = []

    for image in ds.image_files():
        stem = image.stem
        if stem not in preds or ds.label_path(stem).exists() is False:
            continue

        width_height = ds.image_size(stem)
        width = width_height[0] if width_height else 1
        height = width_height[1] if width_height else 1

        predictions = []
        fp_predictions = []
        for pred in preds.get(stem, []):
            cls, conf, cx, cy, w, h = pred
            box = (cx, cy, w, h)
            if conf >= sc["fp_conf"]:
                fp_predictions.append((cls, conf, box))
            area = w * width * h * height
            if conf >= sc["conf"] and area >= sc["min_area_px"]:
                predictions.append((cls, conf, box))

        labels = ds.valid_boxes(stem)

        for cls, conf, pred_box in predictions:
            cands = [
                (lab_cls, lab_box)
                for lab_cls, cx, cy, w, h in labels
                for lab_box in [(cx, cy, w, h)]
                if iou_xywh(pred_box, lab_box) >= sc["iou_missing"]
            ]
            if not cands:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_MISSING",
                                    stem, "Model thấy vật chưa có nhãn",
                                    extra={"conf": conf}))
                continue

            same = [(lab_cls, lab_box) for lab_cls, lab_box in cands if lab_cls == cls]
            if same:
                best_iou = max(iou_xywh(pred_box, lab_box) for _, lab_box in same)
                if best_iou < sc["iou_loose"]:
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_LOOSE_BOX",
                                        stem, "Box nhãn lệch so với vật model thấy",
                                        extra={"conf": conf, "iou": best_iou}))
                continue

            other = [(lab_cls, lab_box) for lab_cls, lab_box in cands if lab_cls != cls]
            if other:
                best_iou = max(iou_xywh(pred_box, lab_box) for _, lab_box in other)
                if best_iou >= sc["iou_match"]:
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_WRONG_CLASS",
                                        stem, "Model dự đoán khác lớp với nhãn",
                                        extra={"conf": conf, "iou": best_iou}))

        label_lines = ds.read_label_lines(stem) or []
        for line_no, text in label_lines:
            try:
                lab_cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError:
                continue
            if not 0 <= lab_cls < len(ds.classes):
                continue
            lab_box = (cx, cy, w, h)
            if not any(iou_xywh(lab_box, fp_box) >= sc["iou_missing"]
                       for _, _, fp_box in fp_predictions):
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_FALSE_POS",
                                    stem, "Không có dự đoán model nào phù hợp với box nhãn",
                                    line_no, {"iou_threshold": sc["iou_missing"]}))

    return issues
