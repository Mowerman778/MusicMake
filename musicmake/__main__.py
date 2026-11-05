"""`python -m musicmake doctor`, or `python -m musicmake [--host 127.0.0.1] [--port 8765] [--data ./data] [--engine auto]`"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    import sys

    if sys.argv[1:2] == ["doctor"]:
        from .doctor import main as doctor

        raise SystemExit(doctor())
    ap = argparse.ArgumentParser(prog="musicmake", description="Private prompt-to-song music maker")
    ap.add_argument("--host", default="127.0.0.1", help="keep 127.0.0.1 so only this computer can reach it")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data", default=os.environ.get("MUSICMAKE_DATA", "data"), help="where songs are stored")
    ap.add_argument("--engine", default=os.environ.get("MUSICMAKE_ENGINE", "auto"),
                    choices=["auto", "sketch", "acestep"])
    ap.add_argument("--acestep-url", default=os.environ.get("ACESTEP_URL", "http://127.0.0.1:8001"))
    args = ap.parse_args()

    os.environ["MUSICMAKE_ENGINE"] = args.engine
    os.environ["ACESTEP_URL"] = args.acestep_url

    import uvicorn

    from .server import create_app

    print(f"MusicMake on http://{args.host}:{args.port}  (songs in {os.path.abspath(args.data)})")
    uvicorn.run(create_app(args.data), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
