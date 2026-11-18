"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    lc = cfg["label_format"]
    issues = []

    for image in ds.image_files():
        stem = image.stem
        label_path = ds.label_path(stem)
        if not label_path.exists():
            continue

        size = ds.image_size(stem)
        previous = []
        lines = label_path.read_text(encoding="utf-8", errors="replace").splitlines()

        for line_no, text in enumerate(lines, 1):
            if not text.strip():
                continue
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem,
                                    "Dòng nhãn không đúng định dạng YOLO", line_no))
                continue

            if not 0 <= cls < len(ds.classes):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                                    f"ID lớp {cls} nằm ngoài phạm vi", line_no,
                                    {"class_id": cls}))
                continue

            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem,
                                    "Cạnh box bằng hoặc nhỏ hơn 0", line_no))
                continue

            left = cx - w / 2
            right = cx + w / 2
            top = cy - h / 2
            bottom = cy + h / 2
            overflow = max(0.0, -left, right - 1.0, -top, bottom - 1.0)
            if overflow > lc["overflow_tol"]:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    "Box tràn khỏi ảnh", line_no, {"overflow": overflow}))

            box = (cx, cy, w, h)
            if any(pcls == cls and iou_xywh(box, pbox) > lc["dup_box_iou"]
                   for pcls, pbox in previous):
                issues.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                    "Box trùng với một dòng nhãn trước đó", line_no,
                                    {"iou_threshold": lc["dup_box_iou"]}))

            previous.append((cls, box))

            if size:
                width, height = size
                short_px = min(w * width, h * height)
                if short_px < lc["min_box_px"]:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                        "Cạnh ngắn của box quá nhỏ", line_no,
                                        {"short_px": short_px}))
                if w * h > lc["max_box_frac"]:
                    issues.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                        "Box chiếm quá lớn diện tích ảnh", line_no,
                                        {"box_frac": w * h}))

    return issues
