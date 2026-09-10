"""Run on the Nano: python3 -m unittest -v test_server.

Optional positive-image check: FACE_TEST_IMAGE=/tmp/face.jpg python3 -m unittest -v.
The fixture stays outside the repository; no camera frame is saved by these tests.
"""
import http.client
import json
import os
import threading
import unittest

import cv2
import numpy as np

from server import make_server, MAX_BODY


class DetectorHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0, "test")
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.blank = cv2.imencode(".jpg", np.zeros((480, 640, 3), np.uint8))[1].tobytes()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def call(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        defaults = {"Origin": f"http://127.0.0.1:{self.port}", "Content-Type": "image/jpeg"}
        defaults.update(headers or {})
        try:
            connection.request(method, path, body=body, headers=defaults)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_blank_frame(self):
        status, body, _ = self.call("POST", "/api/detect", self.blank)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual((result["width"], result["height"]), (640, 480))
        self.assertEqual(result["faces"], [])
        self.assertGreaterEqual(result["processing_ms"], result["inference_ms"])

    def test_real_face_and_coordinate_scaling(self):
        if not os.environ.get("FACE_TEST_IMAGE"):
            self.skipTest("Set FACE_TEST_IMAGE to exercise positive detection")
        image = cv2.imread(os.environ["FACE_TEST_IMAGE"])
        self.assertIsNotNone(image)
        image = cv2.resize(image, (512, 512))
        # Letterboxing verifies both non-square scaling and original-frame coordinates.
        frame = np.zeros((576, 768, 3), np.uint8)
        frame[32:544, 128:640] = image
        jpeg = cv2.imencode(".jpg", frame)[1].tobytes()
        status, body, _ = self.call("POST", "/api/detect", jpeg)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual((result["width"], result["height"]), (768, 576))
        self.assertGreaterEqual(len(result["faces"]), 1)
        for face in result["faces"]:
            x, y, width, height = face["box"]
            self.assertTrue(0 <= x < x + width <= 768)
            self.assertTrue(0 <= y < y + height <= 576)
            self.assertGreaterEqual(face["confidence"], 0.8)
            self.assertEqual(len(face["landmarks"]), 5)
            for lx, ly in face["landmarks"]:
                self.assertTrue(x - width * .25 <= lx <= x + width * 1.25)
                self.assertTrue(y - height * .25 <= ly <= y + height * 1.25)

        # The same face must map consistently when the entire source is scaled.
        smaller = cv2.resize(frame, (384, 288))
        status, body, _ = self.call("POST", "/api/detect", cv2.imencode(".jpg", smaller)[1].tobytes())
        self.assertEqual(status, 200)
        small_faces = json.loads(body)["faces"]
        self.assertGreaterEqual(len(small_faces), 1)
        largest = max(result["faces"], key=lambda face: face["box"][2] * face["box"][3])
        small_largest = max(small_faces, key=lambda face: face["box"][2] * face["box"][3])
        np.testing.assert_allclose(largest["box"], np.array(small_largest["box"]) * 2, atol=12)

    def test_reject_invalid_and_oversized_frames(self):
        self.assertEqual(self.call("POST", "/api/detect", b"not a jpeg")[0], 400)
        oversized = cv2.imencode(".jpg", np.zeros((721, 1281, 3), np.uint8))[1].tobytes()
        self.assertEqual(self.call("POST", "/api/detect", oversized)[0], 400)
        self.assertEqual(self.call("POST", "/api/detect", b"x" * (MAX_BODY + 1))[0], 413)
        self.assertEqual(self.call("POST", "/api/detect", self.blank, {"Content-Type": "text/plain"})[0], 415)

    def test_origin_host_and_static_boundary(self):
        self.assertEqual(self.call("POST", "/api/detect", self.blank, {"Origin": "https://other.example"})[0], 403)
        self.assertEqual(self.call("GET", "/api/health", headers={"Host": "other.example"})[0], 403)
        self.assertEqual(self.call("GET", "/../server.py")[0], 404)
        self.assertEqual(self.call("GET", "/models/face_detection_yunet_2023mar.onnx")[0], 404)
        status, _, headers = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("microphone=()", headers["Permissions-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("POST", "/api/detect", self.blank, {"Content-Type": "image/jpeg"})
            self.assertEqual(connection.getresponse().status, 403)
        finally:
            connection.close()

    def test_busy_detector_rejects_instead_of_queuing(self):
        with self.server.detector.lock:
            self.assertEqual(self.call("POST", "/api/detect", self.blank)[0], 429)
        self.assertEqual(self.call("POST", "/api/detect", self.blank)[0], 200)

    def test_health(self):
        status, body, _ = self.call("GET", "/api/health")
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result["service"], "nano-face")
        self.assertEqual(result["session"], "test")
        self.assertEqual(result["backend"], "OpenCV CPU")


if __name__ == "__main__":
    unittest.main()
