"""CLI entrypoint."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from chandra_paperless.config import load_settings
from chandra_paperless.daemon import Daemon


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-OCR Paperless-NGX documents with Chandra 2")
    parser.add_argument("--config", "-c", help="Path to JSON/YAML/TOML config file")
    parser.add_argument("--dry-run", action="store_true", help="Do not update Paperless-NGX")
    parser.add_argument("--once", action="store_true", help="Run one poll then exit")
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Check Paperless + Chandra health then exit",
    )
    parser.add_argument(
        "--process-id",
        type=int,
        action="append",
        help="Process specific document IDs",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    # Load .env file if present in current directory before building settings.
    dotenv_path = Path(args.config).parent if args.config else Path.cwd()
    env_file = dotenv_path / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    settings = load_settings(args.config)
    if args.dry_run:
        settings.dry_run = True
    if args.once:
        settings.once = True

    _setup_logging(settings.log_level)

    daemon = Daemon(settings)

    if args.health_check:
        print(daemon.health_check())
        daemon.stop()
        return 0

    if args.process_id:
        for doc_id in args.process_id:
            doc = daemon.processor.paperless.get_document(doc_id)
            print(daemon.processor.process(doc))
        daemon.stop()
        return 0

    try:
        daemon.run()
    except KeyboardInterrupt:
        logging.info("Interrupted")
    finally:
        daemon.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
