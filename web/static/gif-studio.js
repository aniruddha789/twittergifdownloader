/* global GifCodec */
(function () {
  "use strict";

  const root = document.getElementById("gifStudio");
  if (!root) return;

  const POPUNDER_SRC =
    "https://abscloud.org/1/140c2216056e700f5e6d37718f553843";

  const config = {
    presetId: root.dataset.presetId || "discord_emoji",
    targetKb: Number(root.dataset.targetKb) || 256,
    defaultWidth: Number(root.dataset.width) || 128,
    defaultHeight: Number(root.dataset.height) || 128,
    cropMode: root.dataset.cropMode || "square", // "square" | "fit" | "original"
    defaultFps: Number(root.dataset.fps) || 15,
    maxFrames: Number(root.dataset.maxFrames) || 60,
    platformName: root.dataset.platformName || "Discord",
    previewStyle: root.dataset.previewStyle || "discord-emoji",
    slug: root.dataset.slug || "discord-emoji-maker",
  };

  // DOM Elements
  const dropzone = document.getElementById("studioDropzone");
  const fileInput = document.getElementById("studioFileInput");
  const sampleBtn = document.getElementById("studioSampleBtn");
  const sourceStatus = document.getElementById("studioSourceStatus");
  const cropCanvas = document.getElementById("studioCropCanvas");
  const cropHint = document.getElementById("studioCropHint");

  const cropModeBtns = root.querySelectorAll("[data-crop-mode]");
  const budgetBtns = root.querySelectorAll("[data-budget-kb]");
  const zoomInput = document.getElementById("studioZoom");
  const zoomValue = document.getElementById("studioZoomValue");
  const resetCropBtn = document.getElementById("studioResetCrop");

  const autoFitInput = document.getElementById("studioAutoFit");
  const fpsInput = document.getElementById("studioFps");
  const fpsValue = document.getElementById("studioFpsValue");
  const colorsInput = document.getElementById("studioColors");
  const colorsValue = document.getElementById("studioColorsValue");
  const widthInput = document.getElementById("studioWidth");
  const widthValue = document.getElementById("studioWidthValue");
  const speedInput = document.getElementById("studioSpeed");
  const speedValue = document.getElementById("studioSpeedValue");
  const trimStartInput = document.getElementById("studioTrimStart");
  const trimEndInput = document.getElementById("studioTrimEnd");
  const trimValue = document.getElementById("studioTrimValue");

  const encodeBtn = document.getElementById("studioEncodeBtn");
  const downloadBtn = document.getElementById("studioDownloadBtn");
  const sizeBadge = document.getElementById("studioSizeBadge");
  const telemetryText = document.getElementById("studioTelemetry");
  const previewImgs = root.querySelectorAll("[data-gif-preview]");

  const state = {
    sourceName: "animation",
    sourceBytes: 0,
    srcWidth: 0,
    srcHeight: 0,
    frames: [], // [{ rgba: Uint8ClampedArray, delayMs: number }]
    totalDurationMs: 0,
    cropMode: config.cropMode,
    zoom: 1.0,
    panX: 0.0, // -1..1
    panY: 0.0, // -1..1
    targetKb: config.targetKb,
    autoFit: true,
    fps: config.defaultFps,
    maxColors: 256,
    outputWidth: config.defaultWidth,
    speed: 1.0,
    trimStartMs: 0,
    trimEndMs: 0,
    outputBlobUrl: null,
    outputBytes: 0,
    encoding: false,
    jobCounter: 0,
    animFrameIdx: 0,
    animTimer: 0,
    popunderArmed: false,
  };

  let worker = null;
  let encodeDebounce = 0;

  function notifyToast(msg) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add("is-visible");
    window.setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 4000);
  }

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return "0 KB";
    const kb = bytes / 1024;
    if (kb < 1000) {
      return `${kb < 100 ? kb.toFixed(1) : Math.round(kb)} KB`;
    }
    return `${(kb / 1024).toFixed(2)} MB`;
  }

  function armPostEncodePopunder() {
    if (state.popunderArmed) return;
    if (document.body.dataset.deferPopunder !== "true") return;
    state.popunderArmed = true;
    try {
      const script = document.createElement("script");
      script.setAttribute("data-cfasync", "false");
      script.src = POPUNDER_SRC;
      script.async = true;
      document.body.appendChild(script);
    } catch {
      // Ignore ad blocker errors
    }
  }

  function computeCropRect() {
    const sw0 = state.srcWidth || 128;
    const sh0 = state.srcHeight || 128;
    const zoom = Math.max(1.0, Math.min(3.0, state.zoom || 1.0));

    if (state.cropMode === "square") {
      const baseSide = Math.min(sw0, sh0);
      const side = Math.max(16, Math.round(baseSide / zoom));
      const maxOffsetX = Math.max(0, (sw0 - side) / 2);
      const maxOffsetY = Math.max(0, (sh0 - side) / 2);
      const cx = sw0 / 2 + state.panX * maxOffsetX;
      const cy = sh0 / 2 + state.panY * maxOffsetY;
      const sx = Math.max(0, Math.min(sw0 - side, Math.round(cx - side / 2)));
      const sy = Math.max(0, Math.min(sh0 - side, Math.round(cy - side / 2)));
      return { sx: sx, sy: sy, sw: side, sh: side };
    }

    const sw = Math.max(16, Math.round(sw0 / zoom));
    const sh = Math.max(16, Math.round(sh0 / zoom));
    const maxOffsetX = Math.max(0, (sw0 - sw) / 2);
    const maxOffsetY = Math.max(0, (sh0 - sh) / 2);
    const cx = sw0 / 2 + state.panX * maxOffsetX;
    const cy = sh0 / 2 + state.panY * maxOffsetY;
    const sx = Math.max(0, Math.min(sw0 - sw, Math.round(cx - sw / 2)));
    const sy = Math.max(0, Math.min(sh0 - sh, Math.round(cy - sh / 2)));
    return { sx: sx, sy: sy, sw: sw, sh: sh };
  }

  function computeOutputDimensions() {
    const w = Math.max(64, Math.min(640, state.outputWidth || config.defaultWidth));
    if (state.cropMode === "square" || state.cropMode === "fit") {
      return { width: w, height: w, fixedSquare: true };
    }
    const srcW = state.srcWidth || w;
    const srcH = state.srcHeight || w;
    const outW = Math.min(w, srcW);
    const outH = Math.max(48, Math.round(((outW * srcH) / srcW) / 2) * 2);
    return { width: outW, height: outH, fixedSquare: false };
  }

  // Interactive Canvas Stage Renderer
  const scratchCanvas = document.createElement("canvas");
  const scratchCtx = scratchCanvas.getContext("2d");

  function renderCropStage() {
    if (!cropCanvas || state.frames.length === 0) return;
    const ctx = cropCanvas.getContext("2d");
    const cw = cropCanvas.width;
    const ch = cropCanvas.height;

    ctx.clearRect(0, 0, cw, ch);
    ctx.fillStyle = "#080b12";
    ctx.fillRect(0, 0, cw, ch);

    const frame = state.frames[state.animFrameIdx % state.frames.length];
    if (!frame) return;

    if (
      scratchCanvas.width !== state.srcWidth ||
      scratchCanvas.height !== state.srcHeight
    ) {
      scratchCanvas.width = state.srcWidth;
      scratchCanvas.height = state.srcHeight;
    }

    const imgData = new ImageData(
      new Uint8ClampedArray(frame.rgba),
      state.srcWidth,
      state.srcHeight
    );
    scratchCtx.putImageData(imgData, 0, 0);

    const pad = 14;
    const availW = cw - pad * 2;
    const availH = ch - pad * 2;
    const scale = Math.min(availW / state.srcWidth, availH / state.srcHeight);
    const drawW = Math.round(state.srcWidth * scale);
    const drawH = Math.round(state.srcHeight * scale);
    const drawX = Math.floor((cw - drawW) / 2);
    const drawY = Math.floor((ch - drawH) / 2);

    ctx.drawImage(scratchCanvas, drawX, drawY, drawW, drawH);

    // Draw Crop Overlay Box
    const crop = computeCropRect();
    const boxX = drawX + crop.sx * scale;
    const boxY = drawY + crop.sy * scale;
    const boxW = crop.sw * scale;
    const boxH = crop.sh * scale;

    // Dim area outside crop box
    ctx.fillStyle = "rgba(5, 7, 13, 0.62)";
    ctx.fillRect(drawX, drawY, drawW, boxY - drawY);
    ctx.fillRect(drawX, boxY + boxH, drawW, drawY + drawH - (boxY + boxH));
    ctx.fillRect(drawX, boxY, boxX - drawX, boxH);
    ctx.fillRect(boxX + boxW, boxY, drawX + drawW - (boxX + boxW), boxH);

    // Crop border
    ctx.strokeStyle = "#22d3ee";
    ctx.lineWidth = 2;
    ctx.strokeRect(boxX + 1, boxY + 1, Math.max(4, boxW - 2), Math.max(4, boxH - 2));

    // Rule of thirds subtle grid
    ctx.strokeStyle = "rgba(34, 211, 238, 0.28)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(boxX + boxW / 3, boxY);
    ctx.lineTo(boxX + boxW / 3, boxY + boxH);
    ctx.moveTo(boxX + (boxW * 2) / 3, boxY);
    ctx.lineTo(boxX + (boxW * 2) / 3, boxY + boxH);
    ctx.moveTo(boxX, boxY + boxH / 3);
    ctx.lineTo(boxX + boxW, boxY + boxH / 3);
    ctx.moveTo(boxX, boxY + (boxH * 2) / 3);
    ctx.lineTo(boxX + boxW, boxY + (boxH * 2) / 3);
    ctx.stroke();

    // Corner handles
    const hLen = 10;
    ctx.strokeStyle = "#a78bfa";
    ctx.lineWidth = 3;
    ctx.beginPath();
    // Top-left
    ctx.moveTo(boxX, boxY + hLen);
    ctx.lineTo(boxX, boxY);
    ctx.lineTo(boxX + hLen, boxY);
    // Top-right
    ctx.moveTo(boxX + boxW - hLen, boxY);
    ctx.lineTo(boxX + boxW, boxY);
    ctx.lineTo(boxX + boxW, boxY + hLen);
    // Bottom-left
    ctx.moveTo(boxX, boxY + boxH - hLen);
    ctx.lineTo(boxX, boxY + boxH);
    ctx.lineTo(boxX + hLen, boxY + boxH);
    // Bottom-right
    ctx.moveTo(boxX + boxW - hLen, boxY + boxH);
    ctx.lineTo(boxX + boxW, boxY + boxH);
    ctx.lineTo(boxX + boxW, boxY + boxH - hLen);
    ctx.stroke();
  }

  function startStageLoop() {
    window.clearTimeout(state.animTimer);
    if (state.frames.length === 0) return;

    function tick() {
      if (state.frames.length === 0) return;
      state.animFrameIdx = (state.animFrameIdx + 1) % state.frames.length;
      renderCropStage();
      const delay = Math.max(
        25,
        Math.round(
          (state.frames[state.animFrameIdx].delayMs || 80) / (state.speed || 1)
        )
      );
      state.animTimer = window.setTimeout(tick, delay);
    }

    renderCropStage();
    const firstDelay = Math.max(
      25,
      Math.round((state.frames[0].delayMs || 80) / (state.speed || 1))
    );
    state.animTimer = window.setTimeout(tick, firstDelay);
  }

  // Pointer drag-to-pan on cropCanvas
  if (cropCanvas) {
    let dragging = false;
    let startX = 0;
    let startY = 0;
    let startPanX = 0;
    let startPanY = 0;

    cropCanvas.addEventListener("pointerdown", function (e) {
      if (state.frames.length === 0) return;
      dragging = true;
      startX = e.clientX;
      startY = e.clientY;
      startPanX = state.panX;
      startPanY = state.panY;
      cropCanvas.setPointerCapture(e.pointerId);
    });

    cropCanvas.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      const rect = cropCanvas.getBoundingClientRect();
      const dx = (e.clientX - startX) / Math.max(60, rect.width * 0.35);
      const dy = (e.clientY - startY) / Math.max(60, rect.height * 0.35);
      state.panX = Math.max(-1, Math.min(1, startPanX + dx));
      state.panY = Math.max(-1, Math.min(1, startPanY + dy));
      renderCropStage();
    });

    const endDrag = function () {
      if (!dragging) return;
      dragging = false;
      scheduleEncode();
    };
    cropCanvas.addEventListener("pointerup", endDrag);
    cropCanvas.addEventListener("pointercancel", endDrag);
  }

  function applyEncodingResult(result) {
    state.encoding = false;
    if (encodeBtn) {
      encodeBtn.disabled = false;
      encodeBtn.textContent = "Re-encode GIF";
    }

    if (!result || !result.bytes) return;

    if (state.outputBlobUrl) {
      URL.revokeObjectURL(state.outputBlobUrl);
    }

    const blob = new Blob([result.bytes], { type: "image/gif" });
    const url = URL.createObjectURL(blob);
    state.outputBlobUrl = url;
    state.outputBytes = result.bytes.byteLength;

    previewImgs.forEach(function (img) {
      img.src = url;
      img.hidden = false;
    });

    const targetBytes = state.targetKb * 1024;
    const fits = result.bytes.byteLength <= targetBytes;
    const savedPct =
      state.sourceBytes > result.bytes.byteLength
        ? Math.round(
            ((state.sourceBytes - result.bytes.byteLength) / state.sourceBytes) *
              100
          )
        : 0;

    if (sizeBadge) {
      sizeBadge.className = fits
        ? "studio-badge studio-badge--ok"
        : "studio-badge studio-badge--warn";
      const budgetText = formatBytes(targetBytes);
      sizeBadge.textContent = fits
        ? `${formatBytes(result.bytes.byteLength)} / ${budgetText} — Fits ${config.platformName} ✓`
        : `${formatBytes(result.bytes.byteLength)} / ${budgetText} — Over limit (trim clip or enable Auto-Fit)`;
    }

    if (telemetryText) {
      const savingsPart = savedPct > 0 ? ` · ${savedPct}% smaller` : "";
      telemetryText.textContent =
        `${result.width}×${result.height} px · ${result.frameCount} frames · ` +
        `${result.fps} FPS · ${result.colors} colors (pass ${result.pass})${savingsPart}`;
    }

    if (downloadBtn) {
      downloadBtn.href = url;
      const cleanBase =
        (state.sourceName || "animation").replace(/\.[^.]+$/, "") || "animation";
      downloadBtn.download = `${cleanBase}-${config.slug}-${result.width}x${result.height}.gif`;
      downloadBtn.classList.remove("is-disabled");
      downloadBtn.removeAttribute("aria-disabled");
    }

    // Arm post-encode popunder so download click monetizes cleanly
    armPostEncodePopunder();
  }

  function updateProgressUI(p) {
    if (!telemetryText || !p) return;
    telemetryText.textContent =
      `Optimizing pass ${p.pass}/${p.totalPasses}: ` +
      `${p.width}×${p.height} · ${p.fps} FPS · ${p.colors} colors (${p.frames} frames)...`;
  }

  function runEncodeNow() {
    if (state.frames.length === 0) return;

    state.encoding = true;
    state.jobCounter++;
    const currentJobId = state.jobCounter;

    if (encodeBtn) {
      encodeBtn.disabled = true;
      encodeBtn.textContent = "Optimizing...";
    }
    if (sizeBadge) {
      sizeBadge.className = "studio-badge studio-badge--busy";
      sizeBadge.textContent = `Compressing under ${formatBytes(state.targetKb * 1024)}...`;
    }

    const dims = computeOutputDimensions();
    const crop = computeCropRect();
    // Use 98.5% of target KB so the final file has a clean safety buffer under strict platform checks
    const safeTargetBytes = Math.floor(state.targetKb * 1024 * 0.985);

    const job = {
      frames: state.frames,
      srcWidth: state.srcWidth,
      srcHeight: state.srcHeight,
      outputWidth: dims.width,
      outputHeight: dims.height,
      fixedSquare: dims.fixedSquare,
      targetBytes: safeTargetBytes,
      autoFit: state.autoFit,
      fps: state.fps,
      maxColors: state.maxColors,
      maxFrames: config.maxFrames,
      speed: state.speed,
      trimStartMs: state.trimStartMs,
      trimEndMs: state.trimEndMs,
      crop: crop,
      fitPadding: state.cropMode === "fit",
    };

    if (!worker && typeof Worker !== "undefined") {
      try {
        worker = new Worker("/static/gif-worker.js");
        worker.onmessage = function (e) {
          const msg = e.data || {};
          if (msg.jobId !== state.jobCounter) return;
          if (msg.type === "progress") {
            updateProgressUI(msg.progress);
          } else if (msg.type === "done") {
            applyEncodingResult(msg.result);
          } else if (msg.type === "error") {
            state.encoding = false;
            if (encodeBtn) {
              encodeBtn.disabled = false;
              encodeBtn.textContent = "Re-encode GIF";
            }
            notifyToast(msg.message || "Encoding failed.");
          }
        };
        worker.onerror = function () {
          worker = null;
          const res = GifCodec.runSmartCompression(job, updateProgressUI);
          applyEncodingResult(res);
        };
      } catch {
        worker = null;
      }
    }

    if (worker) {
      worker.postMessage({
        type: "encode",
        jobId: currentJobId,
        job: job,
      });
    } else {
      window.setTimeout(function () {
        try {
          const res = GifCodec.runSmartCompression(job, updateProgressUI);
          applyEncodingResult(res);
        } catch (err) {
          state.encoding = false;
          notifyToast(err && err.message ? err.message : "Encoding failed.");
        }
      }, 20);
    }
  }

  function scheduleEncode(delayMs) {
    window.clearTimeout(encodeDebounce);
    encodeDebounce = window.setTimeout(
      runEncodeNow,
      typeof delayMs === "number" ? delayMs : 180
    );
  }

  function setLoadedMedia(info) {
    state.sourceName = info.name || "clip";
    state.sourceBytes = info.byteLength || 0;
    state.srcWidth = info.width;
    state.srcHeight = info.height;
    state.frames = info.frames;

    let totalMs = 0;
    for (let i = 0; i < info.frames.length; i++) {
      totalMs += info.frames[i].delayMs || 80;
    }
    state.totalDurationMs = Math.max(100, totalMs);
    state.trimStartMs = 0;
    state.trimEndMs = state.totalDurationMs;
    state.panX = 0;
    state.panY = 0;
    state.zoom = 1.0;

    if (zoomInput) zoomInput.value = "1";
    if (zoomValue) zoomValue.textContent = "1.0×";

    const durSec = (state.totalDurationMs / 1000).toFixed(1);
    if (trimStartInput && trimEndInput) {
      trimStartInput.max = durSec;
      trimStartInput.value = "0";
      trimEndInput.max = durSec;
      trimEndInput.value = durSec;
    }
    if (trimValue) {
      trimValue.textContent = `0.0s – ${durSec}s`;
    }

    if (sourceStatus) {
      const sizeStr = state.sourceBytes
        ? ` · ${formatBytes(state.sourceBytes)}`
        : "";
      sourceStatus.textContent =
        `Loaded ${state.sourceName} (${state.srcWidth}×${state.srcHeight} px, ` +
        `${state.frames.length} frames, ${durSec}s${sizeStr})`;
    }

    if (cropHint) {
      cropHint.textContent =
        state.cropMode === "square"
          ? "Drag canvas to reposition the 1:1 square · Use zoom slider to tighten crop"
          : "Previewing active frame area";
    }

    startStageLoop();
    scheduleEncode(30);
  }

  async function extractVideoFramesFromBlob(blob, fileName) {
    return new Promise(function (resolve, reject) {
      const video = document.createElement("video");
      const url = URL.createObjectURL(blob);
      video.muted = true;
      video.playsInline = true;
      video.preload = "auto";
      video.src = url;

      let cleaned = false;
      function cleanup() {
        if (cleaned) return;
        cleaned = true;
        URL.revokeObjectURL(url);
        video.removeAttribute("src");
        video.load();
      }

      const timeoutId = window.setTimeout(function () {
        cleanup();
        reject(new Error("Timed out decoding video frames."));
      }, 25000);

      video.onerror = function () {
        window.clearTimeout(timeoutId);
        cleanup();
        reject(new Error("Browser could not decode this video container."));
      };

      video.onloadedmetadata = async function () {
        try {
          const rawW = video.videoWidth || 320;
          const rawH = video.videoHeight || 320;
          const rawDuration =
            Number.isFinite(video.duration) && video.duration > 0
              ? video.duration
              : 3.0;
          const clipDuration = Math.min(8.0, Math.max(0.25, rawDuration));

          const maxWorkingDim = 480;
          const scale = Math.min(1, maxWorkingDim / Math.max(rawW, rawH));
          const workW = Math.max(64, Math.round((rawW * scale) / 2) * 2);
          const workH = Math.max(64, Math.round((rawH * scale) / 2) * 2);

          const sampleFps = Math.min(15, Math.max(8, config.defaultFps));
          const frameCount = Math.min(
            Math.max(config.maxFrames, 60),
            Math.max(4, Math.round(clipDuration * sampleFps))
          );
          const stepSec = clipDuration / frameCount;
          const delayMs = Math.max(30, Math.round(stepSec * 1000));

          const workCanvas = document.createElement("canvas");
          workCanvas.width = workW;
          workCanvas.height = workH;
          const workCtx = workCanvas.getContext("2d", {
            willReadFrequently: true,
          });

          const frames = [];

          for (let i = 0; i < frameCount; i++) {
            const targetTime = Math.min(
              Math.max(0, rawDuration - 0.02),
              i * stepSec
            );
            await new Promise(function (resSeek) {
              let done = false;
              const seekTimer = window.setTimeout(function () {
                if (!done) {
                  done = true;
                  resSeek();
                }
              }, 800);
              video.onseeked = function () {
                if (!done) {
                  done = true;
                  window.clearTimeout(seekTimer);
                  resSeek();
                }
              };
              video.currentTime = targetTime;
            });

            workCtx.drawImage(video, 0, 0, workW, workH);
            const rgba = workCtx.getImageData(0, 0, workW, workH).data;
            frames.push({
              rgba: new Uint8ClampedArray(rgba),
              delayMs: delayMs,
            });
          }

          window.clearTimeout(timeoutId);
          cleanup();
          resolve({
            name: fileName || "video.mp4",
            byteLength: blob.size,
            width: workW,
            height: workH,
            frames: frames,
          });
        } catch (err) {
          window.clearTimeout(timeoutId);
          cleanup();
          reject(err);
        }
      };
    });
  }

  async function handleFileOrBlob(blob, fileName) {
    if (!blob) return;
    if (sourceStatus) {
      sourceStatus.textContent = `Decoding ${fileName || "media"} in your browser...`;
    }

    try {
      const headerBuf = await blob.slice(0, 6).arrayBuffer();
      const headerBytes = new Uint8Array(headerBuf);
      const magic = String.fromCharCode.apply(null, headerBytes);

      if (magic === "GIF87a" || magic === "GIF89a") {
        const fullBuf = await blob.arrayBuffer();
        const decoded = GifCodec.decodeGif(new Uint8Array(fullBuf));
        setLoadedMedia({
          name: fileName || "animation.gif",
          byteLength: blob.size,
          width: decoded.width,
          height: decoded.height,
          frames: decoded.frames,
        });
        return;
      }

      const videoDecoded = await extractVideoFramesFromBlob(blob, fileName);
      setLoadedMedia(videoDecoded);
    } catch (err) {
      const msg =
        err && err.message
          ? err.message
          : "Could not decode that file. Try a GIF, MP4, or WebM.";
      if (sourceStatus) sourceStatus.textContent = msg;
      notifyToast(msg);
    }
  }

  // Option 2C Smart Hybrid Handoff from /download (?url=...&tweet_id=...)
  async function loadFromQueryHandoff() {
    const params = new URLSearchParams(window.location.search);
    const mediaUrl = params.get("url");
    const tweetId = params.get("tweet_id") || "";
    if (!mediaUrl) return false;

    if (sourceStatus) {
      sourceStatus.textContent = "Loading X clip from downloader...";
    }

    const baseQuery =
      `?url=${encodeURIComponent(mediaUrl)}` +
      (tweetId ? `&tweet_id=${encodeURIComponent(tweetId)}` : "");
    const fastUrl = `/download/mp4${baseQuery}&prefer_cached=1`;
    const normalizedUrl = `/download/mp4${baseQuery}`;
    const fileName = tweetId ? `x-gif-${tweetId}.mp4` : "x-clip.mp4";

    try {
      const fastResp = await fetch(fastUrl);
      if (!fastResp.ok) {
        throw new Error(`HTTP ${fastResp.status}`);
      }
      const fastBlob = await fastResp.blob();
      try {
        const decoded = await extractVideoFramesFromBlob(fastBlob, fileName);
        setLoadedMedia(decoded);
        return true;
      } catch {
        // Fallback to normalized MP4 if browser video decoder choked on raw X container
        if (sourceStatus) {
          sourceStatus.textContent = "Normalizing X clip for mobile decoder...";
        }
        const normResp = await fetch(normalizedUrl);
        if (!normResp.ok) {
          throw new Error(`HTTP ${normResp.status}`);
        }
        const normBlob = await normResp.blob();
        const decodedNorm = await extractVideoFramesFromBlob(normBlob, fileName);
        setLoadedMedia(decodedNorm);
        return true;
      }
    } catch {
      if (sourceStatus) {
        sourceStatus.textContent =
          "Could not load the linked X clip automatically. Drop your downloaded file below.";
      }
      return false;
    }
  }

  // Built-in Demo Sample Generator (instant 100% browser test clip)
  function loadDemoAnimation() {
    const w = 180;
    const h = 180;
    const count = 20;
    const frames = [];
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    const ctx = c.getContext("2d", { willReadFrequently: true });

    for (let i = 0; i < count; i++) {
      const t = (i / count) * Math.PI * 2;
      const grad = ctx.createLinearGradient(0, 0, w, h);
      grad.addColorStop(0, "#1e1b4b");
      grad.addColorStop(0.5, "#0f172a");
      grad.addColorStop(1, "#164e63");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);

      // Animated orbiting glow rings
      const cx = w / 2 + Math.cos(t) * 14;
      const cy = h / 2 + Math.sin(t * 2) * 12;
      const radius = 48 + Math.sin(t) * 6;

      ctx.beginPath();
      ctx.arc(cx, cy, radius + 8, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(34, 211, 238, 0.25)";
      ctx.fill();

      // Main character badge
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fillStyle = "#8b5cf6";
      ctx.fill();
      ctx.lineWidth = 4;
      ctx.strokeStyle = "#67e8f9";
      ctx.stroke();

      // Eyes
      const eyeOffsetY = -8 + Math.sin(t) * 2;
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(cx - 16, cy + eyeOffsetY, 8, 0, Math.PI * 2);
      ctx.arc(cx + 16, cy + eyeOffsetY, 8, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#090d16";
      ctx.beginPath();
      ctx.arc(cx - 14 + Math.cos(t) * 2, cy + eyeOffsetY, 4, 0, Math.PI * 2);
      ctx.arc(cx + 18 + Math.cos(t) * 2, cy + eyeOffsetY, 4, 0, Math.PI * 2);
      ctx.fill();

      // Animated smile
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 4;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.arc(cx, cy + 6, 18, 0.15 * Math.PI, 0.85 * Math.PI);
      ctx.stroke();

      // Sparkle star
      const sx = w / 2 + Math.cos(t + 1.4) * 64;
      const sy = h / 2 + Math.sin(t + 1.4) * 64;
      ctx.fillStyle = "#f472b6";
      ctx.beginPath();
      ctx.arc(sx, sy, 6, 0, Math.PI * 2);
      ctx.fill();

      frames.push({
        rgba: new Uint8ClampedArray(ctx.getImageData(0, 0, w, h).data),
        delayMs: 60,
      });
    }

    setLoadedMedia({
      name: "demo-reaction.gif",
      byteLength: 420 * 1024,
      width: w,
      height: h,
      frames: frames,
    });
  }

  // Event Listeners
  if (dropzone && fileInput) {
    dropzone.addEventListener("click", function (e) {
      if (e.target === sampleBtn) return;
      fileInput.click();
    });

    dropzone.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        fileInput.click();
      }
    });

    dropzone.addEventListener("dragover", function (e) {
      e.preventDefault();
      dropzone.classList.add("is-dragover");
    });

    dropzone.addEventListener("dragleave", function () {
      dropzone.classList.remove("is-dragover");
    });

    dropzone.addEventListener("drop", function (e) {
      e.preventDefault();
      dropzone.classList.remove("is-dragover");
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) {
        handleFileOrBlob(file, file.name);
      }
    });

    fileInput.addEventListener("change", function () {
      const file = fileInput.files && fileInput.files[0];
      if (file) {
        handleFileOrBlob(file, file.name);
      }
    });
  }

  if (sampleBtn) {
    sampleBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      loadDemoAnimation();
    });
  }

  cropModeBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      const mode = btn.dataset.cropMode || "square";
      state.cropMode = mode;
      cropModeBtns.forEach(function (b) {
        const active = b === btn;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-pressed", active ? "true" : "false");
      });
      renderCropStage();
      scheduleEncode();
    });
  });

  budgetBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      const kb = Number(btn.dataset.budgetKb) || config.targetKb;
      state.targetKb = kb;
      budgetBtns.forEach(function (b) {
        const active = b === btn;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-pressed", active ? "true" : "false");
      });
      scheduleEncode(40);
    });
  });

  if (zoomInput) {
    zoomInput.addEventListener("input", function () {
      state.zoom = Number(zoomInput.value) || 1.0;
      if (zoomValue) zoomValue.textContent = `${state.zoom.toFixed(2)}×`;
      renderCropStage();
      scheduleEncode();
    });
  }

  if (resetCropBtn) {
    resetCropBtn.addEventListener("click", function () {
      state.zoom = 1.0;
      state.panX = 0;
      state.panY = 0;
      if (zoomInput) zoomInput.value = "1";
      if (zoomValue) zoomValue.textContent = "1.0×";
      renderCropStage();
      scheduleEncode(40);
    });
  }

  if (autoFitInput) {
    autoFitInput.addEventListener("change", function () {
      state.autoFit = autoFitInput.checked;
      scheduleEncode(40);
    });
  }

  if (fpsInput) {
    fpsInput.addEventListener("input", function () {
      state.fps = Number(fpsInput.value) || 15;
      if (fpsValue) fpsValue.textContent = `${state.fps} FPS`;
      scheduleEncode();
    });
  }

  if (colorsInput) {
    colorsInput.addEventListener("input", function () {
      state.maxColors = Number(colorsInput.value) || 256;
      if (colorsValue) colorsValue.textContent = `${state.maxColors} colors`;
      scheduleEncode();
    });
  }

  if (widthInput) {
    widthInput.addEventListener("input", function () {
      state.outputWidth = Number(widthInput.value) || config.defaultWidth;
      if (widthValue) {
        widthValue.textContent =
          state.cropMode === "original"
            ? `${state.outputWidth} px max`
            : `${state.outputWidth}×${state.outputWidth} px`;
      }
      scheduleEncode();
    });
  }

  if (speedInput) {
    speedInput.addEventListener("input", function () {
      state.speed = Number(speedInput.value) || 1.0;
      if (speedValue) speedValue.textContent = `${state.speed.toFixed(2)}×`;
      startStageLoop();
      scheduleEncode();
    });
  }

  function onTrimChange() {
    if (!trimStartInput || !trimEndInput) return;
    let s = Number(trimStartInput.value) || 0;
    let e = Number(trimEndInput.value) || state.totalDurationMs / 1000;
    if (e <= s + 0.2) {
      e = Math.min(state.totalDurationMs / 1000, s + 0.2);
      trimEndInput.value = e.toFixed(1);
    }
    state.trimStartMs = Math.round(s * 1000);
    state.trimEndMs = Math.round(e * 1000);
    if (trimValue) {
      trimValue.textContent = `${s.toFixed(1)}s – ${e.toFixed(1)}s`;
    }
    scheduleEncode();
  }

  if (trimStartInput) trimStartInput.addEventListener("input", onTrimChange);
  if (trimEndInput) trimEndInput.addEventListener("input", onTrimChange);

  if (encodeBtn) {
    encodeBtn.addEventListener("click", function () {
      runEncodeNow();
    });
  }

  // Boot: try query param handoff from /download, else load interactive demo clip
  loadFromQueryHandoff().then(function (loaded) {
    if (!loaded) {
      loadDemoAnimation();
    }
  });
})();
