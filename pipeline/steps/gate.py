"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)
    reviewed = set(reviewed)
    n_errors = sum(1 for i in issues if i.severity == ERROR)

    warned = {
        i.image
        for i in issues
        if i.severity == WARN
        and i.image in stems
        and i.image not in reviewed
    }

    n_images = len(stems)
    n_warn_images = len(warned)
    warn_ratio = round(n_warn_images / n_images, 4) if n_images else 0.0
    threshold = cfg["gate"]["warn_ratio_hold"]

    if n_errors:
        decision = "Rework"
        reasons = [f"Còn {n_errors} lỗi bắt buộc nên cần sửa lại"]
    elif warn_ratio >= threshold:
        decision = "Hold"
        reasons = [
            f"{n_warn_images}/{n_images} ảnh còn cảnh báo "
            f"({warn_ratio:.4f}) đạt ngưỡng Hold {threshold:.4f}"
        ]
    else:
        decision = "Release"
        reasons = [
            f"Tỉ lệ cảnh báo chưa duyệt {warn_ratio:.4f} thấp hơn "
            f"ngưỡng Hold {threshold:.4f}"
        ]

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": n_warn_images,
        "n_images": n_images,
        "warn_ratio": warn_ratio,
        "reasons": reasons,
    }
