"""Bounded real-HTTP measurement. Fixture timings are never labeled OSRM SLA results."""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
import numpy as np
from dotenv import dotenv_values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    password = dotenv_values(".env")["RISE_DEMO_PASSWORD"]
    timings = []
    with httpx.Client(base_url=args.base_url, timeout=20) as client:
        client.post(
            "/api/auth/login", json={"email": "passenger@rise.local", "password": password}
        ).raise_for_status()
        system = client.get("/api/system").json()
        for _ in range(args.iterations):
            request = client.post(
                "/api/trip-requests",
                headers={"Idempotency-Key": str(uuid4())},
                json={
                    "pickup": {"lat": 20.961, "lon": 105.747},
                    "dropoff": {"lat": 21.013, "lon": 105.824},
                    "budget_min": 80000,
                    "budget_max": 800000,
                },
            )
            request.raise_for_status()
            started = time.perf_counter()
            response = client.get(f"/api/trip-requests/{request.json()['id']}/recommendations")
            response.raise_for_status()
            timings.append((time.perf_counter() - started) * 1000)
    report = {
        "samples": len(timings),
        "p50_ms": float(np.quantile(timings, 0.5)),
        "p95_ms": float(np.quantile(timings, 0.95)),
        "max_ms": max(timings),
        "system": system,
        "includes_real_osrm": system["routing_mode"] == "osrm",
        "production_sla_verified": False,
        "scope": "SINGLE_CLIENT_LOCAL_HTTP",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"samples": len(timings), "p95_ms": report["p95_ms"], "routing": system["routing_mode"]}
        )
    )


if __name__ == "__main__":
    main()
