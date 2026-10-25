"""Entry point for workflow-cli."""

import sys

from workflow_cli.cli import main as cli_main


def main() -> int:
    """Main entry point. Dispatches to the CLI argument parser."""
    try:
        return cli_main(sys.argv[1:])
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
