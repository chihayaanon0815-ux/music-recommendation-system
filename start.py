"""Run the A/B preview with its own playlist database."""

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5076)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    os.environ["LOCALAPPDATA"] = str(root / "test-user-data")
    from web.graph_snapshot import restore_published_index
    from web.app import app

    restore_published_index(root / "data/processed")
    app.run(host="127.0.0.1", port=args.port, use_reloader=False)


if __name__ == "__main__":
    main()
