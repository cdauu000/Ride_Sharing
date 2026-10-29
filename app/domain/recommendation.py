from typing import Any


def baseline_score(item: dict[str, Any], request: dict[str, Any]) -> float:
    price = item.get("expected_price", item["price"])
    low, high = request["budget_min"], request["budget_max"]
    price_score = 1.0 if price <= low else max(0, 1 - (price - low) / max(1, high - low))
    comfort = (
        (0 if request["is_raining"] else 0.3)
        if item["service_code"] == "BIKE_URBAN"
        else (0.7 if "POOL" in item["service_code"] else 1)
    )
    time = max(0, 1 - (item["pickup_eta_min"] + item["duration_min"]) / 180)
    return (
        0.4 * price_score
        + 0.25 * time
        + 0.1 * (1 - item["detour_ratio"])
        + 0.1 * 0.9
        + 0.05 * ("POOL" in item["service_code"])
        + 0.1 * comfort
    )


def diverse_top_k(items: list[dict[str, Any]], k: int = 6) -> list[dict[str, Any]]:
    ranked = sorted(items, key=lambda item: (-item["score"], item["id"]))
    seeds = {}
    for item in ranked:
        seeds.setdefault(item["service_code"], item)
    selected = list(seeds.values())
    for item in ranked:
        if len(selected) >= max(k, len(seeds)):
            break
        if item not in selected:
            selected.append(item)
    selected.sort(key=lambda item: (-item["score"], item["id"]))
    if selected:
        cheapest = min(selected, key=lambda item: item.get("expected_price", item["price"]))["id"]
        fastest = min(selected, key=lambda item: item["pickup_eta_min"] + item["duration_min"])[
            "id"
        ]
        for i, item in enumerate(selected):
            item["shown_position"] = i + 1
            item["shown_reason"] = (
                "DIVERSITY_SEED" if item is seeds[item["service_code"]] else "RANKED_BY_SCORE"
            )
            item["exposure_propensity"] = 1.0
            item["labels"] = (
                (["Đề xuất"] if i == 0 else [])
                + (["Rẻ nhất"] if item["id"] == cheapest else [])
                + (["Nhanh nhất"] if item["id"] == fastest else [])
                + (["Thoải mái nhất"] if "PRIVATE" in item["service_code"] else [])
            )
    return selected
