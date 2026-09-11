#!/usr/bin/env python3
"""Deploy to the Nano, open a USB SSH tunnel, and launch the Mac camera UI."""

import argparse
import json
from pathlib import Path
import secrets
import shlex
import subprocess
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=10",
       "-o", "ServerAliveCountMax=3"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="nano", help="SSH config alias (default: nano)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.host.startswith("-"):
        parser.error("Use a non-option SSH host and a port between 1024 and 65535")
    model = subprocess.check_output(SSH + [args.host, "cat /proc/device-tree/model"], text=True)
    if "NVIDIA Jetson Orin Nano" not in model:
        raise SystemExit(f"Refusing to deploy to a different board: {model!r}")
    print(f"Deploying to {model.strip(chr(0))}", flush=True)
    subprocess.run(SSH + [args.host, "mkdir -p ~/nano-face"], check=True)
    subprocess.run(["scp", "-q", "-r", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                    str(ROOT / "server.py"), str(ROOT / "static"), str(ROOT / "models"),
                    str(ROOT / "test_server.py"), str(ROOT / "README.md"),
                    f"{args.host}:nano-face/"], check=True)
    session = secrets.token_hex(16)
    remote = "cd ~/nano-face && exec /usr/bin/python3 server.py " + shlex.join(
        ["--port", str(args.port), "--session", session, "--stop-on-stdin-eof"])
    process = subprocess.Popen(SSH + ["-T", "-o", "ExitOnForwardFailure=yes", "-L",
        f"127.0.0.1:{args.port}:127.0.0.1:{args.port}", args.host, remote], stdin=subprocess.PIPE)
    url = f"http://127.0.0.1:{args.port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError("SSH/server exited; see the error above (port may be occupied)")
            try:
                with opener.open(url + "/api/health", timeout=1) as response:
                    health = json.load(response)
                if health.get("session") == session:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Nano server did not become ready")
        print(f"\nOpen {url}\nCamera → USB SSH → {health['hostname']} → face boxes.\n"
              "Press Ctrl+C here to stop the Nano detector and tunnel.\n", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        process.wait()
        if process.returncode:
            raise RuntimeError("SSH connection lost; relaunch to reconnect")
    except KeyboardInterrupt:
        print("\nStopping detector and SSH tunnel…", flush=True)
    finally:
        process.stdin.close()  # EOF stops the remote detector, including on launcher exit.
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
