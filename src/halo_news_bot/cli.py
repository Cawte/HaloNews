from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import load_config, validate_runtime_config
from .runner import fetch_and_queue, publish_queue, run_once
from .storage import JsonStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def _storage(cfg):
    return JsonStorage(cfg.queue_path, cfg.state_path, cfg.log_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Halo News Pro Bot")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Fetch news, queue new items, and publish according to POST_MODE")
    sub.add_parser("fetch", help="Only fetch news and update queue")
    sub.add_parser("publish", help="Only publish eligible queued items")
    sub.add_parser("status", help="Print queue/state status")
    parser.add_argument("--once", action="store_true", help="Compatibility flag; same as command 'run'")

    args = parser.parse_args(argv)
    cfg = load_config()
    command = args.command or ("run" if args.once else "status")

    if command == "run":
        result = run_once(cfg)
    elif command == "fetch":
        result = fetch_and_queue(cfg, _storage(cfg))
    elif command == "publish":
        validate_runtime_config(cfg, need_telegram=True)
        result = publish_queue(cfg, _storage(cfg))
    elif command == "status":
        storage = _storage(cfg)
        result = {"queue_counts": storage.status_counts(), "state": storage.load_state()}
    else:
        parser.print_help()
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
