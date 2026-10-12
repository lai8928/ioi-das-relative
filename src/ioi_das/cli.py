"""Command-line interface for Phase 1 auditing and environment diagnostics."""

import argparse
import json
from pathlib import Path
import sys

from .audit import run_audit, write_json
from .environment import inspect_environment


def load_config(path: Path, output_override: str | None = None) -> dict:
    path = path.expanduser().resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    root = (path.parent / config["project_root"]).resolve()
    for key in ("upstream_dir", "generated_dir", "output_dir"):
        value = output_override if key == "output_dir" and output_override else config[key]
        config[key] = (root / value).resolve()
    config["project_root"] = root
    config["config_path"] = path
    if config.get("target_variable") != "position" or config.get("readout_location") != "N":
        raise ValueError("Phase 1 requires target_variable='position' and readout_location='N'.")
    if config.get("intervention_locations") != ["GOAL_NAME", "N", "N-1", "N-2"]:
        raise ValueError("The Phase 1 audit requires locations GOAL_NAME, N, N-1, and N-2 in that order.")
    if isinstance(config.get("batch_size"), bool) or not isinstance(config.get("batch_size"), int) or config["batch_size"] <= 0:
        raise ValueError("batch_size must be a positive integer.")
    if isinstance(config.get("seed"), bool) or not isinstance(config.get("seed"), int):
        raise ValueError("seed must be an integer.")
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit original IOI POSITION samples using only a tokenizer.")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="Save or reuse original samples and audit per-example positions.")
    audit.add_argument("--config", required=True, type=Path, help="Explicit JSON configuration path.")
    audit.add_argument("--output-dir", help="Output path relative to configured project root, or an absolute path.")
    doctor = commands.add_parser("doctor", help="Inspect dependencies and optionally verify a real CUDA operation.")
    doctor.add_argument("--require-gpu", action="store_true", help="Require CUDA and run a small GPU matrix multiplication.")
    doctor.add_argument("--device", default="cuda:0", help="Logical CUDA device after CUDA_VISIBLE_DEVICES mapping.")
    doctor.add_argument("--output", type=Path, help="Optional explicit JSON report path, resolved from the current directory.")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        report = inspect_environment(args.require_gpu, args.device)
        if args.output:
            write_json(args.output.expanduser().resolve(), report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "passed" else 2
    try:
        config = load_config(args.config, args.output_dir)
        summary = run_audit(config)
    except (OSError, ValueError, KeyError, ImportError, RuntimeError) as error:
        print(f"Audit failed: {error}", file=sys.stderr)
        return 2
    print(f"Audit passed: {summary['counts']['train']} train / {summary['counts']['test']} test pairs; "
          f"{len(summary['unsupported_answer_checks'])} unsupported answer checks.")
    print(f"Dataset {'reused' if summary['dataset_reused'] else 'created'}: {config['generated_dir']}")
    print(f"Evidence: {config['output_dir'] / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
