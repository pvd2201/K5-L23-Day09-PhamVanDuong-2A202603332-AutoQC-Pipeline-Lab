"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    fixes = []
    error_issues = [i for i in issues if i.severity == ERROR]
    if not error_issues:
        return fixes

    removed = {
        i.image for i in error_issues
        if i.code in {"DUP_IMAGE_EXACT", "DUP_IMAGE_PHASH", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
    }

    for stem in sorted(removed):
        image_path = ds.image_path(stem)
        label_path = ds.label_path(stem)
        if image_path is not None and image_path.exists():
            image_path.unlink()
        if label_path.exists():
            label_path.unlink()
        fixes.append({
            "image": stem,
            "line": "",
            "action": "remove_image",
            "before": str(image_path) if image_path else stem,
            "after": "(đã xoá)",
        })

    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    grouped = defaultdict(list)
    for i in error_issues:
        if i.image in removed:
            continue
        if i.code in drop_codes or i.code == "BOX_OUT_OF_IMAGE":
            grouped[i.image].append(i)
        elif i.code == "MISSING_LABEL_FILE":
            fixes.append({
                "image": i.image,
                "line": "",
                "action": "needs_label",
                "before": "(không có file)",
                "after": "chuyển người gán",
            })
        elif i.code == "BAD_CLASS_NAME":
            if ds.yaml_path.exists():
                data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
                data["names"] = list(cfg["classes"])
                ds.yaml_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                                        encoding="utf-8")
            fixes.append({
                "image": "data.yaml",
                "line": "",
                "action": "rename_classes",
                "before": "names cũ",
                "after": ",".join(cfg["classes"]),
            })

    for stem, stem_issues in grouped.items():
        label_path = ds.label_path(stem)
        if not label_path.exists():
            continue

        original = label_path.read_text(encoding="utf-8", errors="replace").splitlines()
        drop_lines = {i.line for i in stem_issues if i.code in drop_codes}
        for i in stem_issues:
            if i.code in drop_codes:
                drop_lines.add(i.line)
        clip_lines = {
            i.line: i
            for i in stem_issues
            if i.code == "BOX_OUT_OF_IMAGE" and i.line not in drop_lines
        }

        affected_lines = sorted(set(drop_lines) | set(clip_lines), reverse=True)
        for line_no in affected_lines:
            idx = line_no - 1
            if 0 <= idx < len(original):
                before = original[idx]
                if line_no in drop_lines:
                    del original[idx]
                    fixes.append({
                        "image": stem,
                        "line": line_no,
                        "action": "drop_line",
                        "before": before,
                        "after": "(xoá dòng)",
                    })
                else:
                    try:
                        cls, cx, cy, w, h = parse_yolo_line(before)
                    except ValueError:
                        continue
                    left = max(0.0, cx - w / 2)
                    right = min(1.0, cx + w / 2)
                    top = max(0.0, cy - h / 2)
                    bottom = min(1.0, cy + h / 2)
                    cw = right - left
                    ch = bottom - top
                    if cw <= 0 or ch <= 0:
                        del original[idx]
                        fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "drop_line",
                            "before": before,
                            "after": "(xoá dòng: box không còn diện tích)",
                        })
                    else:
                        ncx = (left + right) / 2
                        ncy = (top + bottom) / 2
                        after = f"{cls} {ncx:.6g} {ncy:.6g} {cw:.6g} {ch:.6g}"
                        original[idx] = after
                        fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "clip_box",
                            "before": before,
                            "after": after,
                        })

        label_path.write_text("".join(line + "\n" for line in original), encoding="utf-8")

    return fixes
