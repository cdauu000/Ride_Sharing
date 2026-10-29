"""Human-readable places; arbitrary locations retain their actual coordinates."""

from typing import Any

KNOWN_PLACES = (
    (20.961, 105.747, "Đại học Phenikaa, Hà Đông"),
    (21.013, 105.824, "Đống Đa, Hà Nội"),
    (20.983, 105.731, "La Phù, Hoài Đức"),
    (20.995, 105.807, "Nguyễn Trãi, Thanh Xuân"),
    (20.646, 106.051, "TP Hưng Yên"),
    (21.1861, 106.0763, "TP Bắc Ninh"),
)


def location_view(point: dict[str, Any], label: str | None = None) -> dict[str, Any]:
    lat, lon = point["lat"], point["lon"]
    known = next(
        (name for x, y, name in KNOWN_PLACES if abs(lat - x) < 0.00001 and abs(lon - y) < 0.00001),
        None,
    )
    text = (label or "").strip()
    if text in {"Tọa độ tùy chọn", "Vị trí đã chọn trên bản đồ", "Vị trí hiện tại"}:
        text = ""
    return {"lat": lat, "lon": lon, "label": text or known or f"{lat:.5f}, {lon:.5f}"}
