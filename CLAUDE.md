# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Mac browser captures camera frames → JPEG over a USB SSH tunnel → Jetson Orin Nano runs YuNet (OpenCV CPU) → JSON boxes/landmarks drawn back on the same captured frame. No cloud, no recording, no identity recognition. Three pieces, no build step, no Mac Python dependencies:

- `launch.py` — Mac orchestrator: board check, `scp` deploy, `ssh -L` tunnel, health wait, browser open, cleanup.
- `server.py` — Nano loopback-only HTTP server: static allowlist, `/api/health`, `/api/detect`, YuNet inference.
- `static/` — browser UI (`app.js`, `index.html`, `style.css`): `getUserMedia`, capture loop, rendering.

`README.md` is the user-facing spec (API table, detection pipeline, verified results). `NANO.md` is the hardware/OS record for the board (JetPack 7.2.1, SSH aliases, upgrade log). Read both before changing behavior they document; update their dated "verified" sections when re-validating.

## Commands

Run from the Mac:

```bash
python3 launch.py                 # deploy to Nano, tunnel, open http://127.0.0.1:8765
python3 launch.py --no-browser    # same without opening the browser
python3 launch.py --port 8766     # changes both tunnel ends
python3 -m py_compile launch.py server.py test_server.py && node --check static/app.js
```

Tests need OpenCV with `FaceDetectorYN`, which the Mac does not have (`cv2` is not installed here). Run them on the Nano after a deploy:

```bash
ssh nano 'cd ~/nano-face && python3 -m unittest -v test_server'
ssh nano 'cd ~/nano-face && python3 -m unittest -v test_server.DetectorHTTPTests.test_health'
ssh nano 'cd ~/nano-face && FACE_TEST_IMAGE=/tmp/face.jpg python3 -m unittest -v test_server'   # positive-face case, otherwise skipped
```

`launch.py` deploys `test_server.py` too, so a plain launch (Ctrl+C after health) is enough to refresh the Nano copy. Use the Nano's system `/usr/bin/python3` (NVIDIA OpenCV 4.8.0); a venv hides it.

## Architecture invariants

These are enforced by code and tests; changing one usually means changing several files.

- **Deploy list is explicit.** `launch.py` scp's exactly `server.py`, `static/`, `models/`, `test_server.py`, `README.md`. A new runtime file must be added there.
- **Static allowlist is explicit.** `server.py` `STATIC` maps `/`, `/app.js`, `/style.css` only; anything else is 404 (tested). A new static asset must be added there.
- **Model is pinned by SHA-256.** `Detector.__init__` refuses to start unless `models/face_detection_yunet_2023mar.onnx` matches `MODEL_SHA256`. Swapping the model means updating the hash, and the model must stay YuNet 2023mar for OpenCV 4.8 compatibility.
- **One request in flight, no queue.** Server: non-blocking `detector.lock` → 429 when busy. Browser: `tick()` awaits each response before capturing the next frame, capped at 50 ms (20 fps). Do not add server-side queuing.
- **Session binding.** Launcher passes `--session <hex>`; `/api/health` echoes it; launcher only opens the browser when the session matches, so a stale server on the port is rejected.
- **Lifetime tied to SSH stdin.** Server runs with `--stop-on-stdin-eof`; launcher keeps `stdin=PIPE` open and closes it on exit, which shuts the Nano process down. No systemd service, nothing at boot.
- **Trust boundary is loopback.** Server binds `127.0.0.1`; `Host` must be `127.0.0.1:<port>`/`localhost:<port>`; POST requires a matching `Origin`; HTTP/1.0 closes per request so rejected bodies can't be replayed as a new request; body ≤ 1 MB, decoded frame ≤ 1280×720 (also capped via `OPENCV_IO_MAX_*` env before `import cv2`).
- **Coordinates map back to the submitted frame.** Server resizes longest side to 320, runs YuNet, rescales X and Y independently, clips boxes. Browser checks `result.width/height === capture.width/height` and draws on the exact captured canvas, not a live preview. Mirroring transforms frame and geometry together; labels are drawn outside the mirror transform.
- **Browser `generation` counter** invalidates every async continuation after `stop()`; any new async path in `app.js` must re-check `run !== generation` after each await.
- **Launcher refuses other boards.** `/proc/device-tree/model` must contain `NVIDIA Jetson Orin Nano`. The AGX Orin (`jetson` alias) is a separate device; do not target it.

## Board facts that matter for code

- Nano: Python 3.12.3, NumPy 1.26.4, OpenCV 4.8.0 (NVIDIA build, CPU backend deliberately — no CUDA/TensorRT claims). Mac: Python 3.14, stdlib only.
- SSH alias `nano` → `<user>@192.168.55.1` over USB, passwordless key. `NANO.md` lists Ethernet/Wi-Fi alternatives via `-o HostName=...`.
- `.local/` is git-ignored, mode 0700, holds private backups and credentials. Never commit or read into context unless asked.
