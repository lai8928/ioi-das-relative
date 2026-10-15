"""Command-line interface for dataset audits, diagnostics, and configured experiments."""

import argparse
import json
from pathlib import Path
import sys
import tempfile


def load_config(path: Path, output_override: str | None = None) -> dict:
    """Resolve the frozen audit configuration and check its original position contract."""
    path = path.expanduser().resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    root = (path.parent / config["project_root"]).resolve()
    for key in ("upstream_dir", "generated_dir", "output_dir"):
        value = output_override if key == "output_dir" and output_override else config[key]
        config[key] = (root / value).resolve()
    config["project_root"] = root
    config["config_path"] = path
    if config.get("target_variable") != "position" or config.get("readout_location") != "N":
        raise ValueError("Audit requires target_variable='position' and readout_location='N'.")
    if config.get("intervention_locations") != ["GOAL_NAME", "N", "N-1", "N-2"]:
        raise ValueError("Audit requires locations GOAL_NAME, N, N-1, and N-2 in that order.")
    if isinstance(config.get("batch_size"), bool) or not isinstance(config.get("batch_size"), int) or config["batch_size"] <= 0:
        raise ValueError("batch_size must be a positive integer.")
    if isinstance(config.get("seed"), bool) or not isinstance(config.get("seed"), int):
        raise ValueError("seed must be an integer.")
    if (config["output_dir"] / "summary.json").exists():
        if output_override:
            raise ValueError(f"Completed audit exists at {config['output_dir']}; choose a fresh --output-dir.")
        config["output_dir"] = Path(tempfile.mkdtemp(prefix="ioi-das-audit-"))
    return config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run IOI audits, diagnostics, and configured DAS experiments.")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="Reuse original samples and audit per-example positions.")
    audit.add_argument("--config", required=True, type=Path)
    audit.add_argument("--output-dir", help="Fresh audit evidence directory.")
    doctor = commands.add_parser("doctor", help="Inspect dependencies and optionally verify CUDA.")
    doctor.add_argument("--require-gpu", action="store_true")
    doctor.add_argument("--device", default="cuda:0")
    doctor.add_argument("--output", type=Path)
    run = commands.add_parser("run", help="Run all conditions of a resolved experiment config.")
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--smoke", action="store_true", help="Use balanced subsets and one training epoch.")
    run.add_argument("--resume", nargs="?", const=True, default=False, type=Path,
                     help="Verify and resume a matching run, optionally at an explicit directory.")
    run.add_argument("--override", action="append", default=[], metavar="KEY.PATH=JSON")
    report = commands.add_parser("report", help="Rebuild reports from saved evidence without loading a model.")
    report.add_argument("--experiment-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one CLI command and return its process exit status."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "report":
            from .report import generate_report
            report = generate_report(args.experiment_dir)
            print(json.dumps(report, indent=2))
        elif args.command == "doctor":
            from .audit import write_json
            from .environment import inspect_environment
            report = inspect_environment(args.require_gpu, args.device)
            if args.output:
                write_json(args.output.expanduser().resolve(), report)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["status"] == "passed" else 2
        elif args.command == "run":
            from .config import load_config as load_experiment_config
            from .pipeline import run_experiment
            config = load_experiment_config(args.config, args.override)
            result = run_experiment(config, args.smoke, args.resume,
                                    command=[sys.executable, "-m", "ioi_das.cli", *(sys.argv[1:] if argv is None else argv)])
            print(f"Experiment {result['status']}: {result['experiment_dir']}")
            if result["status"] != "complete":
                return 2
        else:
            from .audit import run_audit
            config = load_config(args.config, args.output_dir)
            summary = run_audit(config)
            print(f"Audit passed: {summary['counts']['train']} train / {summary['counts']['test']} test pairs; "
                  f"{len(summary['unsupported_answer_checks'])} unsupported answer checks.")
            print(f"Dataset {'reused' if summary['dataset_reused'] else 'created'}: {config['generated_dir']}")
            print(f"Evidence: {config['output_dir'] / 'summary.md'}")
    except (OSError, ValueError, KeyError, ImportError, RuntimeError, AssertionError) as error:
        print(f"{args.command.capitalize()} failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
