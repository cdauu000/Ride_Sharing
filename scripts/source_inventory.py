"""Hash and index every supplied specification; never alter original evidence."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    "bao_cao_tien_du_an_ride_sharing_revision_9.md",
    "mvp_config_baseline_v1.md",
    "revision_9_decision_register.md",
    "revision_8_to_revision_9_changelog.md",
]


def main() -> None:
    records = []
    text = [
        "# Chỉ mục bằng chứng đặc tả",
        "",
        "Mỗi tệp gốc được đọc toàn bộ để lập chỉ mục, mã băm và đối chiếu cấu trúc. Chỉ mục không thay thế báo cáo phân tích và bằng chứng kiểm thử.",
        "",
    ]
    for name in SOURCES:
        path = ROOT / name
        raw = path.read_bytes()
        content = raw.decode("utf-8-sig")
        lines = content.splitlines()
        headings = [
            {"line": i, "title": line}
            for i, line in enumerate(lines, 1)
            if re.match(r"^#{1,6}\s", line)
        ]
        record = {
            "file": name,
            "bytes": len(raw),
            "lines": len(lines),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "headings": headings,
        }
        records.append(record)
        text.extend(
            [
                f"## {name}",
                "",
                f"{len(lines)} dòng; {len(raw)} bytes; SHA-256 `{record['sha256']}`.",
                "",
                "| Dòng | Nội dung |",
                "|---:|---|",
            ]
        )
        text.extend(
            f"| {entry['line']} | {entry['title'].lstrip('# ').replace('|', ' / ')} |"
            for entry in headings
        )
        text.append("")
    target = ROOT / "docs"
    target.mkdir(exist_ok=True)
    (target / "source_inventory.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (target / "source_inventory.md").write_text("\n".join(text), encoding="utf-8")
    print(
        f"Indexed {len(records)} source files and {sum(len(r['headings']) for r in records)} headings"
    )


if __name__ == "__main__":
    main()
