"""Download public OSM into workspace and build two independent OSRM graphs."""

import argparse
import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ghcr.io/project-osrm/osrm-backend:v5.27.1"
URL = "https://download.geofabrik.de/asia/vietnam-latest.osm.pbf"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pbf", type=Path, help="Existing OSM PBF; otherwise downloads public Vietnam extract"
    )
    args = parser.parse_args()
    if not shutil.which("docker"):
        raise SystemExit("Docker is required for OSRM preprocessing; no graph was generated.")
    source = args.pbf.resolve() if args.pbf else ROOT / "data/osrm/source/vietnam.osm.pbf"
    if not args.pbf and not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, source)
    digest = hashlib.file_digest(source.open("rb"), "sha256").hexdigest()
    for profile in ("car", "motorbike"):
        target = ROOT / "data/osrm" / profile
        target.mkdir(parents=True, exist_ok=True)
        manifest = target / "manifest.json"
        if manifest.exists():
            if json.loads(manifest.read_text())["source_sha256"] != digest:
                raise SystemExit(
                    "Different source exists; select a new versioned output directory first."
                )
            continue
        shutil.copyfile(source, target / "vietnam.osm.pbf")
        mounts = ["-v", f"{target}:/data", "-v", f"{ROOT / 'config'}:/profiles:ro"]
        lua = "/opt/car.lua" if profile == "car" else "/profiles/motorbike.lua"
        commands = [
            ["osrm-extract", "-p", lua, "/data/vietnam.osm.pbf"],
            ["osrm-partition", "/data/vietnam.osrm"],
            ["osrm-customize", "/data/vietnam.osrm"],
        ]
        for command in commands:
            subprocess.run(["docker", "run", "--rm", *mounts, IMAGE, *command], check=True)
        manifest.write_text(
            json.dumps(
                {
                    "source_url": URL if not args.pbf else None,
                    "source_sha256": digest,
                    "profile": profile,
                    "image": IMAGE,
                    "calibration_status": "V03_PENDING",
                }
            ),
            encoding="utf-8",
        )
    print("OSRM car and motorbike graphs generated; run docker compose --profile routing up -d")


if __name__ == "__main__":
    main()
