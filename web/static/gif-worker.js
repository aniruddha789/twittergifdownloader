/* global importScripts, GifCodec */
"use strict";

importScripts("/static/gif-codec.js");

self.onmessage = function (event) {
  const data = event.data || {};
  if (data.type !== "encode") {
    return;
  }

  const jobId = data.jobId;
  try {
    const result = GifCodec.runSmartCompression(data.job, function (progress) {
      self.postMessage({
        type: "progress",
        jobId: jobId,
        progress: progress,
      });
    });

    const buffer = result.bytes.buffer;
    self.postMessage(
      {
        type: "done",
        jobId: jobId,
        result: {
          bytes: result.bytes,
          width: result.width,
          height: result.height,
          fps: result.fps,
          colors: result.colors,
          frameCount: result.frameCount,
          pass: result.pass,
          fitsTarget: result.fitsTarget,
        },
      },
      [buffer]
    );
  } catch (err) {
    self.postMessage({
      type: "error",
      jobId: jobId,
      message: err && err.message ? err.message : "GIF encoding failed.",
    });
  }
};
