"""Small, auditable local corrections for POIs missing from the public index."""

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


def normalize_address(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    return " ".join(
        re.findall(
            r"[a-z0-9]+(?:/[a-z0-9]+)*", "".join(c for c in value if not unicodedata.combining(c))
        )
    )


class PlaceCatalog:
    def __init__(self, path: str) -> None:
        self.places: list[dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))

    def search(self, query: str) -> list[dict[str, Any]]:
        normalized = normalize_address(query)
        tokens = set(normalized.split())
        found = []
        for place in self.places:
            # Explicit conflicting house numbers/districts must never be overridden.
            if set(re.findall(r"\b\d+[a-z]?\b", normalized)) - {place["house_number"]}:
                continue
            if any(area in normalized for area in place.get("excluded_areas", [])):
                continue
            aliases = place["aliases"]
            if not any(set(normalize_address(alias).split()) <= tokens for alias in aliases):
                continue
            allowed = set(normalize_address(place["label"] + " " + " ".join(aliases)).split())
            allowed.update(
                "khach san o tai dia chi duong pho thanh pho tp viet nam vietnam".split()
            )
            if tokens - allowed:
                continue
            found.append(
                {
                    key: place[key]
                    for key in ("id", "lat", "lon", "label", "kind", "source", "precision")
                }
            )
        return found


def relevant_address(query: str, properties: dict[str, Any]) -> bool:
    """Reject fuzzy results that contradict a requested house number or POI name."""
    normalized = normalize_address(query)
    requested_numbers = [
        match.group()
        for match in re.finditer(r"\b\d+[a-z]?(?:/\d+[a-z]?)*\b", normalized)
        if not normalized[: match.start()]
        .rstrip()
        .endswith(("duong", "pho", "ngo", "ngach", "hem", "quoc lo", "ql", "dt"))
    ]
    house = normalize_address(str(properties.get("housenumber", "")))
    if requested_numbers and house not in requested_numbers:
        return False
    if requested_numbers:
        common = set(
            "duong pho so ngo ngach hem p phuong quan q huyen thi tran tp thanh pho ha noi hanoi viet nam vietnam khach san hotel".split()
        )
        required = set(normalized.split()) - common - set(requested_numbers)
        actual = set(
            normalize_address(" ".join(str(value) for value in properties.values())).split()
        )
        if not required <= actual:
            return False
    # Photon sometimes substitutes any hotel for a missing named hotel.
    words = normalized.split()
    if "hotel" in words:
        name = normalize_address(str(properties.get("name", "")))
        index = words.index("hotel")
        if index and words[index - 1] not in name.split():
            return False
    return True
