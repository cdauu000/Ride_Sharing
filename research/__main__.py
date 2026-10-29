"""Command-line research pipeline. Run with python -m research --help."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.data import (
    canonical_bytes,
    censor_unavailable_outcomes,
    read_dataset,
    temporal_split,
    write_dataset,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to replace immutable report: {path}")
    path.write_bytes(canonical_bytes(value))


def _lineage() -> dict[str, Any]:
    import hashlib
    import importlib.metadata

    versions = {}
    for package in ("numpy", "scikit-learn", "lightgbm", "scipy", "pyarrow"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "NOT_INSTALLED"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "UNCOMMITTED_WORKSPACE"
    root = Path(__file__).resolve().parents[1]
    code = {
        str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for folder in ("app", "research")
        for path in sorted((root / folder).rglob("*.py"))
    }
    return {
        "python": platform.python_version(),
        "libraries": versions,
        "git_commit_sha": commit,
        "code_sha256": code,
        "baseline_sha256": hashlib.sha256(
            (root / "config/mvp_config_baseline_v1.yaml").read_bytes()
        ).hexdigest(),
    }


def _configuration(args: argparse.Namespace) -> Any:
    from research.simulator import SimulationConfig

    return SimulationConfig(
        master_seed=args.seed,
        request_count=args.requests,
        days=args.days,
        urban_density=args.density,
        intercity_density=args.intercity_density,
        rain_share=args.rain_share,
    )


def simulate(args: argparse.Namespace) -> None:
    from app.routing import FixtureRouting, OsrmRouting
    from research.domain_engine import DomainSimulationEngine
    from research.simulator import Simulator

    config = _configuration(args)
    routing = (
        FixtureRouting()
        if args.routing == "fixture"
        else OsrmRouting(
            os.environ.get("RISE_OSRM_CAR_URL", "http://localhost:5000"),
            os.environ.get("RISE_OSRM_MOTORBIKE_URL", "http://localhost:5001"),
        )
    )
    result = Simulator(
        config, DomainSimulationEngine(config, routing, batch_matching=args.batch)
    ).run()
    manifest = write_dataset(result.rows, Path(args.output), dict(result.manifest, **_lineage()))
    _write_json(Path(args.output) / "metrics.json", result.metrics)
    print(
        json.dumps(
            {
                "dataset": str(Path(args.output) / "observations.jsonl"),
                "sha256": manifest["sha256"],
                "rows": len(result.rows),
                "metrics": result.metrics,
            },
            ensure_ascii=False,
        )
    )


def train(args: argparse.Namespace) -> None:
    from research.evaluation import offline_report
    from research.models import save_bundle, train_bundle

    rows = read_dataset(Path(args.dataset))
    splits = temporal_split(rows)
    train_end = min(str(row["timestamp_utc"]) for row in splits["VAL"])
    val_end = min(str(row["timestamp_utc"]) for row in splits["TEST"])
    observed_train = censor_unavailable_outcomes(splits["TRAIN"], train_end)
    observed_validation = censor_unavailable_outcomes(splits["VAL"], val_end)
    bundle = train_bundle(observed_train, observed_validation, args.version)
    bundle.manifest.update(_lineage())
    bundle.manifest.update(
        {
            "dataset": str(args.dataset),
            "pricing_versions": sorted(
                {str(row.get("pricing_version", "UNKNOWN")) for row in rows}
            ),
            "scenario_versions": sorted(
                {str(row.get("scenario_version", "UNKNOWN")) for row in rows}
            ),
            "outcome_embargo_train": train_end,
            "outcome_embargo_validation": val_end,
        }
    )
    manifest = save_bundle(bundle, Path(args.output))
    report = offline_report(bundle, splits["TEST"], observed_train)
    _write_json(Path(args.output) / "offline_report.json", report)
    print(
        json.dumps(
            {
                "model": args.output,
                "version": args.version,
                "train_queries": manifest["train_queries"],
                "validation_queries": manifest["validation_queries"],
                "match_calibration_status": manifest["match_calibration_status"],
                "selection_validation_ece": manifest["selection_validation_ece"],
                "report": str(Path(args.output) / "offline_report.json"),
            },
            ensure_ascii=False,
        )
    )


def closed_loop(args: argparse.Namespace) -> None:
    from research.evaluation import closed_loop_report
    from research.models import load_bundle

    start, end = (int(value) for value in args.seeds.split(":"))
    if end < start:
        raise ValueError("Seed interval must be ascending and inclusive")
    bundle = load_bundle(Path(args.model))
    report = closed_loop_report(
        bundle,
        _configuration(args),
        list(range(start, end + 1)),
        full_scenario_matrix=not args.single_scenario,
    )
    _write_json(
        Path(args.output),
        dict(
            report,
            lineage=_lineage(),
            model_version=bundle.version,
            configuration=asdict(_configuration(args)),
        ),
    )
    print(
        json.dumps(
            {
                "report": args.output,
                "seeds": len(report["seeds"]),
                "scenarios": len(report["scenarios"]),
                "main_benchmark_ready": report["main_benchmark_ready"],
            }
        )
    )


def survey(args: argparse.Namespace) -> None:
    from research.survey import (
        SurveyResponse,
        fairness_analysis,
        respondent_cross_validation,
        survey_quality,
    )

    source = Path(args.responses)
    payload = json.loads(source.read_text(encoding="utf-8"))
    responses = [SurveyResponse.model_validate(item) for item in payload]
    report = {
        "quality": survey_quality(responses),
        "H4": fairness_analysis(responses),
        "cross_validation": respondent_cross_validation(responses)
        if len(responses) >= 5
        else {"status": "INSUFFICIENT_RESPONDENTS"},
    }
    _write_json(Path(args.output), report)
    print(json.dumps({"report": args.output, "quality": report["quality"]}))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Revision 9 reproducible research; synthetic evidence is labeled explicitly"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def simulation_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--seed", type=int, default=1000)
        command.add_argument("--requests", type=int, default=1000)
        command.add_argument("--days", type=int, default=28)
        command.add_argument("--density", choices=["LOW", "MEDIUM", "HIGH"], default="MEDIUM")
        command.add_argument(
            "--intercity-density", choices=["LOW", "MEDIUM", "HIGH"], default="MEDIUM"
        )
        command.add_argument("--rain-share", type=float, default=0.1)

    command = commands.add_parser("simulate")
    simulation_arguments(command)
    command.add_argument("--routing", choices=["fixture", "osrm"], default="fixture")
    command.add_argument("--batch", action="store_true")
    command.add_argument("--output", required=True)
    command.set_defaults(action=simulate)
    command = commands.add_parser("train")
    command.add_argument("--dataset", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--version", default="ltr_v9_001")
    command.set_defaults(action=train)
    command = commands.add_parser("closed-loop")
    simulation_arguments(command)
    command.add_argument("--model", required=True)
    command.add_argument("--seeds", default="1000:1019", help="Inclusive seed interval")
    command.add_argument(
        "--single-scenario",
        action="store_true",
        help="Smoke only; full benchmark uses all 18 density/weather cells",
    )
    command.add_argument("--output", required=True)
    command.set_defaults(action=closed_loop)
    command = commands.add_parser("survey")
    command.add_argument(
        "--responses", required=True, help="JSON array of anonymous real responses"
    )
    command.add_argument("--output", required=True)
    command.set_defaults(action=survey)
    args = parser.parse_args()
    args.action(args)


if __name__ == "__main__":
    main()
