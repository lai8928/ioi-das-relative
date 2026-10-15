"""Command-line interface for dataset audits, diagnostics, and configured experiments."""

import argparse
import json
from pathlib import Path
import sys


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run IOI audits, diagnostics, and configured DAS experiments.")
    commands = parser.add_subparsers(dest="command", required=True)
    dataset = commands.add_parser("data", help="Build or audit registered datasets.")
    data_commands = dataset.add_subparsers(dest="data_command", required=True)
    build = data_commands.add_parser("build", help="Build and register a dataset without overwriting files.")
    build.add_argument("--config", required=True, type=Path)
    audit = data_commands.add_parser("audit", help="Audit every saved split of a registered dataset.")
    audit.add_argument("--dataset", required=True)
    audit.add_argument("--config", type=Path, help="Use the tokenizer from an experiment config.")
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
    status = commands.add_parser("status", help="Read run.json counts, elapsed time and estimated finish.")
    status.add_argument("--experiment-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one CLI command and return its process exit status."""
    args = _parser().parse_args(argv)
    command = [sys.executable, "-m", "ioi_das.cli", *(sys.argv[1:] if argv is None else argv)]
    try:
        if args.command == "report":
            from .report import generate_report
            report = generate_report(args.experiment_dir)
            print(json.dumps(report, indent=2))
        elif args.command == "status":
            from .status import format_status, read_status
            print(format_status(read_status(args.experiment_dir)))
        elif args.command == "doctor":
            from .audit import write_json
            from .environment import inspect_environment
            report = inspect_environment(args.require_gpu, args.device)
            if args.output:
                write_json(args.output.expanduser().resolve(), report)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["status"] == "passed" else 2
        elif args.command == "run":
            from .config import load_config
            from .pipeline import run_experiment
            result = run_experiment(load_config(args.config, args.override), args.smoke, args.resume,
                                    command=command)
            print(f"Experiment {result['status']}: {result['experiment_dir']}")
            if result["status"] != "complete":
                return 2
        elif args.data_command == "build":
            from .datasets import build_dataset
            result = build_dataset(args.config)
            print(json.dumps(result, indent=2))
        else:
            from .audit import run_audit
            options = {"tokenizer_config": args.config} if args.config else {}
            summary = run_audit(args.dataset, command=command, **options)
            print(f"Audit {summary['status']}: {summary['counts']}; "
                  f"{len(summary['unsupported_answer_checks'])} unsupported answer checks.")
            print(f"Evidence: {Path(summary['output_dir']) / 'summary.md'}")
            if summary["status"] != "passed":
                return 2
    except (OSError, ValueError, KeyError, ImportError, RuntimeError, AssertionError) as error:
        label = "Data " + args.data_command if args.command == "data" else args.command.capitalize()
        print(f"{label} failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
