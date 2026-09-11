"use strict";
const $ = (id) => document.getElementById(id);
const video = $("video"), view = $("view"), ctx = view.getContext("2d");
const capture = document.createElement("canvas");
const captureCtx = capture.getContext("2d");
let stream = null, generation = 0, request = null;
let ready = false, frames = 0, startedAt = 0;
const HIDDEN = "Camera paused because this tab was hidden. Start again when ready.";

function status(message) { $("status").textContent = message; }
function resetMetrics() {
  for (const id of ["faces", "fps", "inference", "latency"]) $(id).textContent = "—";
}
function stop(message = "Camera stopped. No frames are being sent.") {
  generation++;
  request?.abort(); request = null;
  stream?.getTracks().forEach((track) => track.stop());
  stream = null; video.srcObject = null;
  ctx.clearRect(0, 0, view.width, view.height);
  captureCtx.clearRect(0, 0, capture.width, capture.height);
  $("placeholder").hidden = false;
  $("start").disabled = !ready; $("stop").disabled = true; $("camera").disabled = false;
  $("live").textContent = "CAMERA OFF"; $("live").classList.remove("good");
  $("frame-state").textContent = "No frames captured";
  resetMetrics(); status(message);
}

function render(result) {
  if (view.width !== capture.width || view.height !== capture.height) {
    view.width = capture.width; view.height = capture.height;
  }
  ctx.save();
  if ($("mirror").checked) { ctx.translate(view.width, 0); ctx.scale(-1, 1); }
  ctx.drawImage(capture, 0, 0);
  ctx.lineWidth = 2.5; ctx.strokeStyle = "#c4f26a"; ctx.fillStyle = "#c4f26a";
  for (const face of result.faces) {
    ctx.strokeRect(...face.box);
    if ($("landmarks").checked) {
      for (const [x, y] of face.landmarks) {
        ctx.beginPath(); ctx.arc(x, y, 2.5, 0, 2 * Math.PI); ctx.fill();
      }
    }
  }
  ctx.restore();
  // Labels are outside the mirrored transform, so text remains readable.
  ctx.font = "12px system-ui";
  for (const face of result.faces) {
    const [x, y, w] = face.box;
    const left = $("mirror").checked ? view.width - x - w : x;
    const top = Math.max(16, y - 6);
    const label = `${Math.round(face.confidence * 100)}% face`;
    ctx.fillStyle = "#101713dd"; ctx.fillRect(left, top - 14, 68, 19);
    ctx.fillStyle = "#c4f26a"; ctx.fillText(label, left + 4, top);
  }
}

async function tick(run) {
  if (run !== generation || !stream) return;
  const began = performance.now();
  const ratio = Math.min(640 / video.videoWidth, 480 / video.videoHeight, 1);
  capture.width = Math.max(1, Math.round(video.videoWidth * ratio));
  capture.height = Math.max(1, Math.round(video.videoHeight * ratio));
  captureCtx.drawImage(video, 0, 0, capture.width, capture.height);
  try {
    const blob = await new Promise((resolve) => capture.toBlob(resolve, "image/jpeg", 0.8));
    if (run !== generation) return;
    if (!blob) throw new Error("Could not encode the camera frame");
    request = new AbortController();
    const response = await fetch("/api/detect", {
      method: "POST", headers: {"Content-Type": "image/jpeg"}, body: blob,
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(5000)])
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Nano detection failed");
    if (run !== generation) return;
    if (result.width !== capture.width || result.height !== capture.height) {
      throw new Error("Frame size mismatch; restart the camera");
    }
    render(result);
    frames++;
    $("faces").textContent = result.faces.length;
    $("fps").textContent = (frames / ((performance.now() - startedAt) / 1000)).toFixed(1);
    $("inference").textContent = result.inference_ms.toFixed(0);
    $("latency").textContent = (performance.now() - began).toFixed(0);
    $("dimensions").textContent = `${result.width} × ${result.height}`;
    $("frame-state").textContent = `FRAME ${frames} · MATCHED DETECTION`;
    $("placeholder").hidden = true;
    $("live").textContent = "● LIVE"; $("live").classList.add("good");
    const message = result.faces.length ? "Following face positions on the Nano." : "No face in view. Try facing the camera in good light.";
    if ($("status").textContent !== message) status(message);
    // One request at a time: slow detection drops capture opportunities, not queues frames.
    setTimeout(() => tick(run), Math.max(0, 50 - (performance.now() - began)));
  } catch (error) {
    if (run !== generation) return;
    stop(error.name === "TimeoutError" ? "Nano timed out. Check the USB cable and launcher, then restart the camera." : error.message);
  }
}

async function start() {
  stop();
  const run = generation;
  $("start").disabled = true; $("stop").disabled = false; $("camera").disabled = true;
  status("Waiting for camera permission…");
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("Open this app at http://127.0.0.1:8765 to use the Mac camera.");
    const selected = $("camera").value;
    const acquired = await navigator.mediaDevices.getUserMedia({
      audio: false, video: {width: {ideal: 640}, height: {ideal: 480}, frameRate: {ideal: 20},
        ...(selected ? {deviceId: {exact: selected}} : {facingMode: "user"})}
    });
    if (run !== generation || document.hidden) {
      acquired.getTracks().forEach((track) => track.stop());
      if (run === generation) stop(HIDDEN);
      return;
    }
    stream = acquired; video.srcObject = stream;
    await video.play();
    if (run !== generation) return;
    stream.getVideoTracks()[0].addEventListener("ended", () => {
      if (run === generation) stop("Camera disconnected. Reconnect it and start again.");
    });
    const devices = await navigator.mediaDevices.enumerateDevices();
    if (run !== generation) return;
    const activeId = stream.getVideoTracks()[0].getSettings().deviceId;
    $("camera").replaceChildren(...devices.filter((device) => device.kind === "videoinput").map((device, index) => {
      const option = new Option(device.label || `Camera ${index + 1}`, device.deviceId);
      option.selected = device.deviceId === activeId; return option;
    }));
    frames = 0; startedAt = performance.now();
    $("live").textContent = "DETECTING…"; status("Sending the first frame to the Nano…");
    tick(run);
  } catch (error) {
    if (run !== generation) return;
    const messages = {
      NotAllowedError: "Camera permission denied. Allow camera access for this page and browser in macOS System Settings, then try again.",
      NotFoundError: "No camera found. Connect a camera and try again.",
      NotReadableError: "Camera unavailable. Close other camera apps and try again.",
      OverconstrainedError: "Selected camera is unavailable. Reload to use the default camera."
    };
    stop(messages[error.name] || error.message);
  }
}

$("start").addEventListener("click", start);
$("stop").addEventListener("click", () => stop());
window.addEventListener("pagehide", () => stop());
document.addEventListener("visibilitychange", () => {
  if (document.hidden && !$("stop").disabled) stop(HIDDEN);
});

async function health() {
  try {
    const response = await fetch("/api/health", {signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error("Detector unavailable");
    const data = await response.json();
    if (data.service !== "nano-face") throw new Error("Wrong service on this port");
    const wasReady = ready;
    ready = true; $("connection").textContent = "● NANO CONNECTED"; $("connection").classList.add("good");
    $("backend").textContent = `${data.hostname} · ${data.model} · ${data.backend}`;
    if (!stream && $("stop").disabled) {
      $("start").disabled = false;
      if (!wasReady) status("Nano is ready. Start your Mac camera to begin.");
    }
  } catch (error) {
    ready = false; $("connection").textContent = "NANO DISCONNECTED"; $("connection").classList.remove("good");
    $("start").disabled = true;
    if (stream) stop("Connection lost. Check USB and restart the launcher.");
    else status("Nano is unavailable. Keep the launcher running and check the USB cable.");
  }
}
health(); setInterval(health, 10000);
