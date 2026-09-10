#!/usr/bin/env python3
"""Loopback-only YuNet service. Camera capture and display live in the Mac browser."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Bound decoded image allocation before importing OpenCV.
os.environ["OPENCV_IO_MAX_IMAGE_PIXELS"] = str(1280 * 720)
os.environ["OPENCV_IO_MAX_IMAGE_WIDTH"] = "1280"
os.environ["OPENCV_IO_MAX_IMAGE_HEIGHT"] = "720"
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "models/face_detection_yunet_2023mar.onnx"
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
MAX_BODY = 1_000_000
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}


class Detector:
    def __init__(self):
        if hashlib.sha256(MODEL.read_bytes()).hexdigest() != MODEL_SHA256:
            raise RuntimeError("YuNet model checksum mismatch; redeploy the app")
        cv2.setNumThreads(2)
        self.model = cv2.FaceDetectorYN.create(
            str(MODEL), "", (320, 320), 0.8, 0.3, 500,
            cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)
        self.lock = threading.Lock()

    def detect(self, jpeg):
        started = time.perf_counter()
        if not jpeg.startswith(b"\xff\xd8"):
            raise ValueError("Expected a JPEG frame")
        try:
            frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        except cv2.error as exc:
            raise ValueError("Invalid or oversized JPEG") from exc
        if frame is None:
            raise ValueError("Invalid JPEG")
        height, width = frame.shape[:2]
        if width > 1280 or height > 720:
            raise ValueError("Maximum frame size is 1280 x 720")
        # Preserve aspect ratio; map detections back to the submitted frame.
        scale = min(1.0, 320 / max(width, height))
        small = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))))
        self.model.setInputSize((small.shape[1], small.shape[0]))
        inference_started = time.perf_counter()
        _, rows = self.model.detect(small)
        inference_ms = (time.perf_counter() - inference_started) * 1000
        sx, sy = width / small.shape[1], height / small.shape[0]
        faces = []
        for row in rows if rows is not None else []:
            x, y, w, h = map(float, row[:4])
            x1, y1 = max(0.0, x * sx), max(0.0, y * sy)
            x2, y2 = min(float(width), (x + w) * sx), min(float(height), (y + h) * sy)
            if x2 <= x1 or y2 <= y1:
                continue
            faces.append({"box": [x1, y1, x2 - x1, y2 - y1],
                          "landmarks": [[float(row[i]) * sx, float(row[i + 1]) * sy]
                                        for i in range(4, 14, 2)],
                          "confidence": float(row[14])})
        return {"width": width, "height": height, "faces": faces,
                "inference_ms": round(inference_ms, 2),
                "processing_ms": round((time.perf_counter() - started) * 1000, 2)}


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 deliberately closes each request: rejected bodies cannot become
    # a subsequent request. Browser backpressure limits request frequency.
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass  # Do not log per-frame requests or camera data.

    def reply(self, status, body, content_type="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(self), microphone=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' blob:; media-src 'self' blob:; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def trusted_request(self, require_origin=False):
        if self.headers.get("Host") not in self.server.allowed_hosts:
            self.reply(403, {"error": "Use the localhost SSH tunnel"})
            return False
        origin = self.headers.get("Origin")
        if (require_origin or origin) and origin not in self.server.allowed_origins:
            self.reply(403, {"error": "Origin not allowed"})
            return False
        return True

    def do_GET(self):
        if not self.trusted_request():
            return
        if self.path == "/api/health":
            self.reply(200, {"service": "nano-face", "hostname": socket.gethostname(),
                             "model": "YuNet 2023mar", "backend": "OpenCV CPU",
                             "opencv": cv2.__version__, "session": self.server.session})
        elif self.path in STATIC:
            filename, content_type = STATIC[self.path]
            self.reply(200, (ROOT / "static" / filename).read_bytes(), content_type)
        else:
            self.reply(404, {"error": "Not found"})

    def do_POST(self):
        if not self.trusted_request(require_origin=True):
            return
        if self.path != "/api/detect":
            self.reply(404, {"error": "Not found"})
            return
        if self.headers.get("Content-Type") != "image/jpeg" or self.headers.get("Transfer-Encoding"):
            self.reply(415, {"error": "Send a JPEG body with Content-Length"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BODY:
            self.reply(413, {"error": "Frame must be between 1 byte and 1 MB"})
            return
        if not self.server.detector.lock.acquire(blocking=False):
            self.reply(429, {"error": "Detector busy; use one camera tab"})
            return
        try:
            jpeg = self.rfile.read(length)
            if len(jpeg) != length:
                raise ValueError("Incomplete JPEG body")
            result = self.server.detector.detect(jpeg)
            self.reply(200, result)
        except (ValueError, TimeoutError) as exc:
            self.reply(400, {"error": str(exc)})
        except cv2.error:
            self.reply(500, {"error": "Detection failed; restart the Nano app"})
        finally:
            self.server.detector.lock.release()


def make_server(port=8765, session="manual"):
    detector = Detector()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    actual_port = server.server_address[1]
    server.allowed_hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
    server.allowed_origins = {f"http://{host}" for host in server.allowed_hosts}
    server.detector = detector
    server.session = session
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--session", default="manual")
    parser.add_argument("--stop-on-stdin-eof", action="store_true")
    args = parser.parse_args()
    server = make_server(args.port, args.session)
    if args.stop_on_stdin_eof:
        def watch_connection():
            while sys.stdin.buffer.read(1):
                pass
            server.shutdown()
        threading.Thread(target=watch_connection, daemon=True).start()
    print(f"YuNet ready on 127.0.0.1:{args.port} ({socket.gethostname()}, CPU)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
