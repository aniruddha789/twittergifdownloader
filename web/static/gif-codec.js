(function (root) {
  "use strict";

  const INTERLACE_OFFSETS = [0, 4, 2, 1];
  const INTERLACE_STEPS = [8, 8, 4, 2];
  const BAYER_4X4 = [
    -7, 1, -5, 3,
    5, -3, 7, -1,
    -4, 4, -6, 2,
    8, 0, 6, -2,
  ];

  function nextPow2Bits(count) {
    let bits = 2;
    while ((1 << bits) < count && bits < 8) {
      bits++;
    }
    return bits;
  }

  function lzwDecode(minCodeSize, data, pixelCount) {
    const clearCode = 1 << minCodeSize;
    const endCode = clearCode + 1;
    const output = new Uint8Array(pixelCount);
    const prefix = new Int32Array(4096);
    const suffix = new Uint8Array(4096);
    const stack = new Uint8Array(4096);

    let codeSize = minCodeSize + 1;
    let codeMask = (1 << codeSize) - 1;
    let available = clearCode + 2;
    let oldCode = -1;
    let firstChar = 0;

    for (let i = 0; i < clearCode; i++) {
      prefix[i] = -1;
      suffix[i] = i;
    }

    let bitBuffer = 0;
    let bitCount = 0;
    let dataPos = 0;
    let outPos = 0;
    let stackTop = 0;

    while (outPos < pixelCount) {
      while (bitCount < codeSize && dataPos < data.length) {
        bitBuffer |= data[dataPos++] << bitCount;
        bitCount += 8;
      }
      if (bitCount < codeSize) {
        break;
      }

      const code = bitBuffer & codeMask;
      bitBuffer >>= codeSize;
      bitCount -= codeSize;

      if (code === clearCode) {
        codeSize = minCodeSize + 1;
        codeMask = (1 << codeSize) - 1;
        available = clearCode + 2;
        oldCode = -1;
        continue;
      }
      if (code === endCode) {
        break;
      }

      if (oldCode === -1) {
        if (code < available) {
          output[outPos++] = suffix[code];
          oldCode = code;
          firstChar = suffix[code];
        }
        continue;
      }

      const inCode = code;
      let curCode = code;

      if (curCode >= available) {
        stack[stackTop++] = firstChar;
        curCode = oldCode;
      }

      while (curCode >= clearCode && stackTop < 4095) {
        stack[stackTop++] = suffix[curCode];
        curCode = prefix[curCode];
      }

      firstChar = suffix[curCode];
      stack[stackTop++] = firstChar;

      if (available < 4096) {
        prefix[available] = oldCode;
        suffix[available] = firstChar;
        available++;
        if ((available & codeMask) === 0 && available < 4096) {
          codeSize++;
          codeMask = (1 << codeSize) - 1;
        }
      }

      oldCode = inCode;
      while (stackTop > 0 && outPos < pixelCount) {
        output[outPos++] = stack[--stackTop];
      }
    }

    return output;
  }

  function decodeGif(buffer) {
    const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
    if (bytes.length < 13) {
      throw new Error("Invalid GIF file (too short).");
    }
    const header = String.fromCharCode(
      bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5]
    );
    if (header !== "GIF87a" && header !== "GIF89a") {
      throw new Error("Not a valid GIF87a/GIF89a file.");
    }

    let pos = 6;
    const width = bytes[pos] | (bytes[pos + 1] << 8);
    const height = bytes[pos + 2] | (bytes[pos + 3] << 8);
    const packed = bytes[pos + 4];
    pos += 7;

    if (width <= 0 || height <= 0 || width > 4096 || height > 4096) {
      throw new Error("Unsupported GIF dimensions.");
    }

    let globalPalette = null;
    if (packed & 0x80) {
      const gctSize = 1 << ((packed & 0x07) + 1);
      globalPalette = bytes.subarray(pos, pos + gctSize * 3);
      pos += gctSize * 3;
    }

    const canvas = new Uint8ClampedArray(width * height * 4);
    let previousCanvas = null;
    const frames = [];

    let delayCs = 10;
    let disposal = 0;
    let transparentIndex = -1;

    function readSubBlocks() {
      const chunks = [];
      let total = 0;
      while (pos < bytes.length) {
        const size = bytes[pos++];
        if (size === 0) break;
        const end = Math.min(bytes.length, pos + size);
        chunks.push(bytes.subarray(pos, end));
        total += end - pos;
        pos = end;
      }
      const merged = new Uint8Array(total);
      let offset = 0;
      for (let i = 0; i < chunks.length; i++) {
        merged.set(chunks[i], offset);
        offset += chunks[i].length;
      }
      return merged;
    }

    function skipSubBlocks() {
      while (pos < bytes.length) {
        const size = bytes[pos++];
        if (size === 0) break;
        pos = Math.min(bytes.length, pos + size);
      }
    }

    while (pos < bytes.length) {
      const blockId = bytes[pos++];
      if (blockId === 0x3b) {
        break;
      }

      if (blockId === 0x21) {
        const label = bytes[pos++];
        if (label === 0xf9) {
          const blockSize = bytes[pos++];
          if (blockSize >= 4) {
            const gcePacked = bytes[pos];
            disposal = (gcePacked >> 2) & 0x07;
            const hasTrans = (gcePacked & 0x01) !== 0;
            delayCs = bytes[pos + 1] | (bytes[pos + 2] << 8);
            transparentIndex = hasTrans ? bytes[pos + 3] : -1;
          }
          pos += blockSize;
          skipSubBlocks();
        } else {
          skipSubBlocks();
        }
        continue;
      }

      if (blockId === 0x2c) {
        const frameLeft = bytes[pos] | (bytes[pos + 1] << 8);
        const frameTop = bytes[pos + 2] | (bytes[pos + 3] << 8);
        const frameW = bytes[pos + 4] | (bytes[pos + 5] << 8);
        const frameH = bytes[pos + 6] | (bytes[pos + 7] << 8);
        const imgPacked = bytes[pos + 8];
        pos += 9;

        let palette = globalPalette;
        if (imgPacked & 0x80) {
          const lctSize = 1 << ((imgPacked & 0x07) + 1);
          palette = bytes.subarray(pos, pos + lctSize * 3);
          pos += lctSize * 3;
        }
        const interlaced = (imgPacked & 0x40) !== 0;
        const minCodeSize = bytes[pos++];
        const lzwData = readSubBlocks();

        if (!palette) {
          continue;
        }

        if (disposal === 3) {
          previousCanvas = new Uint8ClampedArray(canvas);
        }

        const indexStream = lzwDecode(minCodeSize, lzwData, frameW * frameH);

        if (!interlaced) {
          for (let y = 0; y < frameH; y++) {
            const dstY = frameTop + y;
            if (dstY < 0 || dstY >= height) continue;
            const srcRow = y * frameW;
            const dstRow = dstY * width;
            for (let x = 0; x < frameW; x++) {
              const dstX = frameLeft + x;
              if (dstX < 0 || dstX >= width) continue;
              const idx = indexStream[srcRow + x];
              if (idx === transparentIndex) continue;
              const pOffset = idx * 3;
              const dOffset = (dstRow + dstX) * 4;
              canvas[dOffset] = palette[pOffset] || 0;
              canvas[dOffset + 1] = palette[pOffset + 1] || 0;
              canvas[dOffset + 2] = palette[pOffset + 2] || 0;
              canvas[dOffset + 3] = 255;
            }
          }
        } else {
          let srcY = 0;
          for (let pass = 0; pass < 4; pass++) {
            for (
              let y = INTERLACE_OFFSETS[pass];
              y < frameH;
              y += INTERLACE_STEPS[pass]
            ) {
              const dstY = frameTop + y;
              const srcRow = srcY * frameW;
              srcY++;
              if (dstY < 0 || dstY >= height) continue;
              const dstRow = dstY * width;
              for (let x = 0; x < frameW; x++) {
                const dstX = frameLeft + x;
                if (dstX < 0 || dstX >= width) continue;
                const idx = indexStream[srcRow + x];
                if (idx === transparentIndex) continue;
                const pOffset = idx * 3;
                const dOffset = (dstRow + dstX) * 4;
                canvas[dOffset] = palette[pOffset] || 0;
                canvas[dOffset + 1] = palette[pOffset + 1] || 0;
                canvas[dOffset + 2] = palette[pOffset + 2] || 0;
                canvas[dOffset + 3] = 255;
              }
            }
          }
        }

        const delayMs = Math.max(20, (delayCs <= 1 ? 10 : delayCs) * 10);
        frames.push({
          rgba: new Uint8ClampedArray(canvas),
          delayMs: delayMs,
        });

        if (disposal === 2) {
          for (let y = 0; y < frameH; y++) {
            const dstY = frameTop + y;
            if (dstY < 0 || dstY >= height) continue;
            const dstRow = dstY * width;
            for (let x = 0; x < frameW; x++) {
              const dstX = frameLeft + x;
              if (dstX < 0 || dstX >= width) continue;
              const dOffset = (dstRow + dstX) * 4;
              canvas[dOffset] = 0;
              canvas[dOffset + 1] = 0;
              canvas[dOffset + 2] = 0;
              canvas[dOffset + 3] = 0;
            }
          }
        } else if (disposal === 3 && previousCanvas) {
          canvas.set(previousCanvas);
        }

        delayCs = 10;
        disposal = 0;
        transparentIndex = -1;
        continue;
      }

      break;
    }

    if (frames.length === 0) {
      throw new Error("No animation frames found in GIF.");
    }

    return {
      width: width,
      height: height,
      frames: frames,
    };
  }

  function buildMedianCutPalette(frames, maxColors) {
    const targetOpaque = Math.max(2, Math.min(255, maxColors - 1));
    const hist = new Uint32Array(32768);
    const totalFrames = frames.length;
    const frameStride = Math.max(1, Math.floor(totalFrames / 24));

    for (let f = 0; f < totalFrames; f += frameStride) {
      const rgba = frames[f].rgba;
      const len = rgba.length;
      const pixelStep = len > 16384 * 4 ? 8 : 4;
      for (let i = 0; i < len; i += pixelStep) {
        if (rgba[i + 3] < 128) continue;
        const r5 = rgba[i] >> 3;
        const g5 = rgba[i + 1] >> 3;
        const b5 = rgba[i + 2] >> 3;
        hist[(r5 << 10) | (g5 << 5) | b5]++;
      }
    }

    const distinct = [];
    for (let key = 0; key < 32768; key++) {
      const count = hist[key];
      if (count > 0) {
        distinct.push({
          r: ((key >> 10) & 31) * 8 + 4,
          g: ((key >> 5) & 31) * 8 + 4,
          b: (key & 31) * 8 + 4,
          count: count,
        });
      }
    }

    if (distinct.length === 0) {
      distinct.push({ r: 0, g: 0, b: 0, count: 1 });
    }

    function createBox(items) {
      let rMin = 255, rMax = 0;
      let gMin = 255, gMax = 0;
      let bMin = 255, bMax = 0;
      let count = 0;
      for (let i = 0; i < items.length; i++) {
        const c = items[i];
        if (c.r < rMin) rMin = c.r;
        if (c.r > rMax) rMax = c.r;
        if (c.g < gMin) gMin = c.g;
        if (c.g > gMax) gMax = c.g;
        if (c.b < bMin) bMin = c.b;
        if (c.b > bMax) bMax = c.b;
        count += c.count;
      }
      return {
        items: items,
        rRange: rMax - rMin,
        gRange: gMax - gMin,
        bRange: bMax - bMin,
        count: count,
      };
    }

    const boxes = [createBox(distinct)];

    while (boxes.length < targetOpaque) {
      let bestIdx = -1;
      let bestScore = 0;
      for (let i = 0; i < boxes.length; i++) {
        const box = boxes[i];
        if (box.items.length < 2) continue;
        const maxSpan = Math.max(box.rRange, box.gRange, box.bRange);
        if (maxSpan === 0) continue;
        const score = maxSpan * Math.sqrt(box.count);
        if (score > bestScore) {
          bestScore = score;
          bestIdx = i;
        }
      }
      if (bestIdx === -1) break;

      const target = boxes[bestIdx];
      const channel =
        target.gRange >= target.rRange && target.gRange >= target.bRange
          ? "g"
          : target.rRange >= target.bRange
            ? "r"
            : "b";

      target.items.sort(function (a, b) {
        return a[channel] - b[channel];
      });

      const halfCount = target.count >> 1;
      let acc = 0;
      let splitAt = 1;
      for (let i = 0; i < target.items.length - 1; i++) {
        acc += target.items[i].count;
        if (acc >= halfCount) {
          splitAt = i + 1;
          break;
        }
      }

      const leftItems = target.items.slice(0, splitAt);
      const rightItems = target.items.slice(splitAt);
      boxes.splice(bestIdx, 1, createBox(leftItems), createBox(rightItems));
    }

    const paletteBits = nextPow2Bits(boxes.length + 1);
    const tableSize = 1 << paletteBits;
    const palette = new Uint8Array(tableSize * 3);

    // Index 0 is reserved for transparency / delta-unchanged pixels
    palette[0] = 0;
    palette[1] = 0;
    palette[2] = 0;

    const actualColors = Math.min(tableSize - 1, boxes.length);
    for (let i = 0; i < actualColors; i++) {
      const items = boxes[i].items;
      let rSum = 0, gSum = 0, bSum = 0, total = 0;
      for (let j = 0; j < items.length; j++) {
        const item = items[j];
        rSum += item.r * item.count;
        gSum += item.g * item.count;
        bSum += item.b * item.count;
        total += item.count;
      }
      const pIdx = (i + 1) * 3;
      palette[pIdx] = total ? Math.round(rSum / total) : 0;
      palette[pIdx + 1] = total ? Math.round(gSum / total) : 0;
      palette[pIdx + 2] = total ? Math.round(bSum / total) : 0;
    }

    const lut = new Int16Array(32768);
    lut.fill(-1);

    function nearestIndex(r, g, b) {
      const r5 = Math.max(0, Math.min(31, r >> 3));
      const g5 = Math.max(0, Math.min(31, g >> 3));
      const b5 = Math.max(0, Math.min(31, b >> 3));
      const key = (r5 << 10) | (g5 << 5) | b5;
      const cached = lut[key];
      if (cached !== -1) return cached;

      const rc = r5 * 8 + 4;
      const gc = g5 * 8 + 4;
      const bc = b5 * 8 + 4;
      let best = 1;
      let bestDist = 1e9;
      for (let i = 1; i <= actualColors; i++) {
        const pIdx = i * 3;
        const dr = rc - palette[pIdx];
        const dg = gc - palette[pIdx + 1];
        const db = bc - palette[pIdx + 2];
        const dist = dr * dr * 2 + dg * dg * 4 + db * db;
        if (dist < bestDist) {
          bestDist = dist;
          best = i;
          if (dist === 0) break;
        }
      }
      lut[key] = best;
      return best;
    }

    return {
      palette: palette,
      paletteBits: paletteBits,
      nearestIndex: nearestIndex,
    };
  }

  function lzwEncode(indices, minCodeSize, outBytes) {
    const clearCode = 1 << minCodeSize;
    const endCode = clearCode + 1;

    outBytes.push(minCodeSize);

    const table = new Int32Array(4096 * 256);
    table.fill(-1);

    let codeSize = minCodeSize + 1;
    let nextCode = endCode + 1;
    let maxCode = 1 << codeSize;

    let bitBuffer = 0;
    let bitCount = 0;
    const subBlock = new Uint8Array(255);
    let subLen = 0;

    function flushSubBlock() {
      if (subLen > 0) {
        outBytes.push(subLen);
        for (let i = 0; i < subLen; i++) {
          outBytes.push(subBlock[i]);
        }
        subLen = 0;
      }
    }

    function emitCode(code) {
      bitBuffer |= code << bitCount;
      bitCount += codeSize;
      while (bitCount >= 8) {
        subBlock[subLen++] = bitBuffer & 0xff;
        if (subLen === 255) {
          flushSubBlock();
        }
        bitBuffer >>= 8;
        bitCount -= 8;
      }
    }

    emitCode(clearCode);

    if (indices.length === 0) {
      emitCode(endCode);
      if (bitCount > 0) {
        subBlock[subLen++] = bitBuffer & 0xff;
      }
      flushSubBlock();
      outBytes.push(0);
      return;
    }

    let prefix = indices[0];

    for (let i = 1; i < indices.length; i++) {
      const k = indices[i];
      const slot = (prefix << 8) | k;
      const existing = table[slot];

      if (existing !== -1) {
        prefix = existing;
      } else {
        emitCode(prefix);
        if (nextCode < 4096) {
          table[slot] = nextCode++;
          if (nextCode > maxCode && codeSize < 12) {
            codeSize++;
            maxCode = 1 << codeSize;
          }
        } else {
          emitCode(clearCode);
          table.fill(-1);
          codeSize = minCodeSize + 1;
          nextCode = endCode + 1;
          maxCode = 1 << codeSize;
        }
        prefix = k;
      }
    }

    emitCode(prefix);
    emitCode(endCode);

    if (bitCount > 0) {
      subBlock[subLen++] = bitBuffer & 0xff;
    }
    flushSubBlock();
    outBytes.push(0);
  }

  function writeInt16LE(out, val) {
    out.push(val & 0xff, (val >> 8) & 0xff);
  }

  function encodeGif(options) {
    const width = options.width;
    const height = options.height;
    const frames = options.frames;
    const maxColors = Math.max(8, Math.min(256, options.maxColors || 256));
    const dither = Boolean(options.dither);
    const deltaTolerance = typeof options.deltaTolerance === "number"
      ? options.deltaTolerance
      : 6;

    const quant = buildMedianCutPalette(frames, maxColors);
    const palette = quant.palette;
    const paletteBits = quant.paletteBits;
    const nearestIndex = quant.nearestIndex;

    const out = [];
    // GIF89a magic
    out.push(0x47, 0x49, 0x46, 0x38, 0x39, 0x61);
    writeInt16LE(out, width);
    writeInt16LE(out, height);

    const gctFlag = 0x80 | ((paletteBits - 1) << 4) | (paletteBits - 1);
    out.push(gctFlag, 0, 0);

    for (let i = 0; i < palette.length; i++) {
      out.push(palette[i]);
    }

    // NETSCAPE2.0 infinite loop extension
    out.push(
      0x21, 0xff, 0x0b,
      0x4e, 0x45, 0x54, 0x53, 0x43, 0x41, 0x50, 0x45, 0x32, 0x2e, 0x30,
      0x03, 0x01, 0x00, 0x00, 0x00
    );

    const pixelCount = width * height;
    const screenIndices = new Uint8Array(pixelCount);
    const screenR = new Uint8Array(pixelCount);
    const screenG = new Uint8Array(pixelCount);
    const screenB = new Uint8Array(pixelCount);
    let canDelta = true;

    for (let f = 0; f < frames.length; f++) {
      const rgba = frames[f].rgba;
      for (let i = 3; i < rgba.length; i += 4) {
        if (rgba[i] < 128) {
          canDelta = false;
          break;
        }
      }
      if (!canDelta) break;
    }

    const tolSq = deltaTolerance * deltaTolerance * 3;

    for (let f = 0; f < frames.length; f++) {
      const frame = frames[f];
      const rgba = frame.rgba;
      const delayCs = Math.max(2, Math.round((frame.delayMs || 80) / 10));

      const fullIndices = new Uint8Array(pixelCount);
      let minX = width, minY = height, maxX = -1, maxY = -1;

      for (let y = 0; y < height; y++) {
        const rowOffset = y * width;
        const bayerRow = (y & 3) << 2;
        for (let x = 0; x < width; x++) {
          const p = rowOffset + x;
          const p4 = p << 2;
          const a = rgba[p4 + 3];

          if (a < 128) {
            fullIndices[p] = 0;
            if (f === 0 || screenIndices[p] !== 0) {
              if (x < minX) minX = x;
              if (x > maxX) maxX = x;
              if (y < minY) minY = y;
              if (y > maxY) maxY = y;
            }
            screenIndices[p] = 0;
            continue;
          }

          let r = rgba[p4];
          let g = rgba[p4 + 1];
          let b = rgba[p4 + 2];

          if (f > 0 && canDelta) {
            const dr = r - screenR[p];
            const dg = g - screenG[p];
            const db = b - screenB[p];
            if (dr * dr + dg * dg + db * db <= tolSq) {
              fullIndices[p] = 0;
              continue;
            }
          }

          if (dither) {
            const offset = BAYER_4X4[bayerRow + (x & 3)];
            r = Math.max(0, Math.min(255, r + offset));
            g = Math.max(0, Math.min(255, g + offset));
            b = Math.max(0, Math.min(255, b + offset));
          }

          const idx = nearestIndex(r, g, b);
          if (f > 0 && canDelta && idx === screenIndices[p]) {
            fullIndices[p] = 0;
            continue;
          }

          fullIndices[p] = idx;
          screenIndices[p] = idx;
          const palOff = idx * 3;
          screenR[p] = palette[palOff];
          screenG[p] = palette[palOff + 1];
          screenB[p] = palette[palOff + 2];

          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }

      let subX = 0, subY = 0, subW = width, subH = height;
      let subIndices = fullIndices;

      if (f > 0 && canDelta) {
        if (maxX < minX || maxY < minY) {
          subX = 0;
          subY = 0;
          subW = 1;
          subH = 1;
          subIndices = new Uint8Array(1);
          subIndices[0] = 0;
        } else {
          subX = minX;
          subY = minY;
          subW = maxX - minX + 1;
          subH = maxY - minY + 1;
          if (subW < width || subH < height) {
            subIndices = new Uint8Array(subW * subH);
            for (let row = 0; row < subH; row++) {
              const srcStart = (subY + row) * width + subX;
              subIndices.set(
                fullIndices.subarray(srcStart, srcStart + subW),
                row * subW
              );
            }
          }
        }
      }

      // Graphic Control Extension
      // disposal = 1 (do not dispose) when canDelta, else disposal = 2 (restore bg)
      const disposalMethod = canDelta ? 1 : 2;
      const gcePacked = (disposalMethod << 2) | 0x01;
      out.push(0x21, 0xf9, 0x04, gcePacked);
      writeInt16LE(out, delayCs);
      out.push(0x00, 0x00);

      // Image Descriptor
      out.push(0x2c);
      writeInt16LE(out, subX);
      writeInt16LE(out, subY);
      writeInt16LE(out, subW);
      writeInt16LE(out, subH);
      out.push(0x00);

      lzwEncode(subIndices, Math.max(2, paletteBits), out);
    }

    // Trailer
    out.push(0x3b);
    return new Uint8Array(out);
  }

  function resampleAndScaleFrames(sourceFrames, srcW, srcH, plan) {
    const outW = plan.width;
    const outH = plan.height;
    const crop = plan.crop;
    const frameIndices = plan.frameIndices;
    const delays = plan.delays;
    const fitPadding = Boolean(plan.fitPadding);

    const outFrames = new Array(frameIndices.length);

    for (let i = 0; i < frameIndices.length; i++) {
      const srcRgba = sourceFrames[frameIndices[i]].rgba;
      const dstRgba = new Uint8ClampedArray(outW * outH * 4);

      if (fitPadding) {
        const scale = Math.min(outW / crop.sw, outH / crop.sh);
        const drawW = Math.max(1, Math.round(crop.sw * scale));
        const drawH = Math.max(1, Math.round(crop.sh * scale));
        const offsetX = Math.floor((outW - drawW) / 2);
        const offsetY = Math.floor((outH - drawH) / 2);

        for (let y = 0; y < drawH; y++) {
          const sy = Math.min(
            srcH - 1,
            Math.max(0, Math.floor(crop.sy + ((y + 0.5) / drawH) * crop.sh))
          );
          const dstRow = (y + offsetY) * outW;
          const srcRow = sy * srcW;
          for (let x = 0; x < drawW; x++) {
            const sx = Math.min(
              srcW - 1,
              Math.max(0, Math.floor(crop.sx + ((x + 0.5) / drawW) * crop.sw))
            );
            const sIdx = (srcRow + sx) << 2;
            const dIdx = (dstRow + (x + offsetX)) << 2;
            dstRgba[dIdx] = srcRgba[sIdx];
            dstRgba[dIdx + 1] = srcRgba[sIdx + 1];
            dstRgba[dIdx + 2] = srcRgba[sIdx + 2];
            dstRgba[dIdx + 3] = srcRgba[sIdx + 3];
          }
        }
      } else {
        for (let y = 0; y < outH; y++) {
          const sy = Math.min(
            srcH - 1,
            Math.max(0, Math.floor(crop.sy + ((y + 0.5) / outH) * crop.sh))
          );
          const dstRow = y * outW;
          const srcRow = sy * srcW;
          for (let x = 0; x < outW; x++) {
            const sx = Math.min(
              srcW - 1,
              Math.max(0, Math.floor(crop.sx + ((x + 0.5) / outW) * crop.sw))
            );
            const sIdx = (srcRow + sx) << 2;
            const dIdx = (dstRow + x) << 2;
            dstRgba[dIdx] = srcRgba[sIdx];
            dstRgba[dIdx + 1] = srcRgba[sIdx + 1];
            dstRgba[dIdx + 2] = srcRgba[sIdx + 2];
            dstRgba[dIdx + 3] = srcRgba[sIdx + 3];
          }
        }
      }

      outFrames[i] = {
        rgba: dstRgba,
        delayMs: delays[i],
      };
    }

    return outFrames;
  }

  function selectFrameTimeline(sourceFrames, trimStartMs, trimEndMs, targetFps, maxFrames, speedMultiplier) {
    const speed = Math.max(0.25, Math.min(4, speedMultiplier || 1));
    let elapsed = 0;
    const clipped = [];

    for (let i = 0; i < sourceFrames.length; i++) {
      const f = sourceFrames[i];
      const dur = Math.max(20, f.delayMs || 80);
      const frameStart = elapsed;
      const frameEnd = elapsed + dur;
      elapsed = frameEnd;

      if (frameEnd <= trimStartMs) continue;
      if (trimEndMs > trimStartMs && frameStart >= trimEndMs) break;
      clipped.push({ index: i, delayMs: dur });
    }

    if (clipped.length === 0) {
      clipped.push({ index: 0, delayMs: 80 });
    }

    let totalClipMs = 0;
    for (let i = 0; i < clipped.length; i++) {
      totalClipMs += clipped[i].delayMs;
    }

    const effectiveDurationMs = Math.max(60, totalClipMs / speed);
    const minIntervalMs = Math.round(1000 / Math.max(4, Math.min(30, targetFps)));
    const desiredCount = Math.max(
      1,
      Math.min(
        clipped.length,
        maxFrames || 90,
        Math.ceil(effectiveDurationMs / minIntervalMs)
      )
    );

    const chosenIndices = [];
    const chosenDelays = [];

    if (desiredCount >= clipped.length) {
      for (let i = 0; i < clipped.length; i++) {
        chosenIndices.push(clipped[i].index);
        chosenDelays.push(Math.max(20, Math.round(clipped[i].delayMs / speed)));
      }
    } else {
      const baseDelay = Math.max(20, Math.round(effectiveDurationMs / desiredCount));
      for (let k = 0; k < desiredCount; k++) {
        const pick = Math.min(
          clipped.length - 1,
          Math.floor((k * clipped.length) / desiredCount)
        );
        chosenIndices.push(clipped[pick].index);
        chosenDelays.push(baseDelay);
      }
    }

    return {
      frameIndices: chosenIndices,
      delays: chosenDelays,
    };
  }

  function runSmartCompression(job, onProgress) {
    const sourceFrames = job.frames;
    const srcW = job.srcWidth;
    const srcH = job.srcHeight;
    const baseW = job.outputWidth;
    const baseH = job.outputHeight;
    const targetBytes = job.targetBytes;
    const autoFit = Boolean(job.autoFit);
    const baseFps = job.fps || 15;
    const baseColors = job.maxColors || 256;
    const maxFrames = job.maxFrames || 60;
    const speed = job.speed || 1;
    const trimStartMs = job.trimStartMs || 0;
    const trimEndMs = job.trimEndMs || 0;
    const crop = job.crop || { sx: 0, sy: 0, sw: srcW, sh: srcH };
    const fitPadding = Boolean(job.fitPadding);
    const isFixedSquare = Boolean(job.fixedSquare);

    const candidates = [];

    if (!autoFit || targetBytes <= 0) {
      candidates.push({
        scale: 1.0,
        fps: baseFps,
        colors: baseColors,
        tol: 5,
        dither: baseColors >= 128,
      });
    } else {
      // Iterative Smart Auto-Compression Ladder:
      // 1. Try target dimensions with clean palette steps (256 -> 128 -> 64)
      // 2. Step FPS down (15 -> 12 -> 10 -> 8) & increase temporal delta tolerance
      // 3. Step palette to 48 / 32 colors
      // 4. Step dimensions down if still above target byte ceiling
      const ladder = [
        { scale: 1.0, fps: baseFps, colors: Math.min(baseColors, 256), tol: 5, dither: true },
        { scale: 1.0, fps: baseFps, colors: Math.min(baseColors, 128), tol: 8, dither: false },
        { scale: 1.0, fps: Math.min(baseFps, 12), colors: Math.min(baseColors, 96), tol: 11, dither: false },
        { scale: 1.0, fps: Math.min(baseFps, 10), colors: Math.min(baseColors, 64), tol: 14, dither: false },
        { scale: 1.0, fps: Math.min(baseFps, 8), colors: Math.min(baseColors, 48), tol: 18, dither: false },
        { scale: 0.85, fps: Math.min(baseFps, 10), colors: 48, tol: 18, dither: false },
        { scale: 0.72, fps: Math.min(baseFps, 8), colors: 32, tol: 22, dither: false },
        { scale: 0.58, fps: 7, colors: 24, tol: 26, dither: false },
      ];
      for (let i = 0; i < ladder.length; i++) {
        candidates.push(ladder[i]);
      }
    }

    let bestResult = null;

    for (let pass = 0; pass < candidates.length; pass++) {
      const step = candidates[pass];
      const w = isFixedSquare && step.scale === 1.0
        ? baseW
        : Math.max(48, Math.round((baseW * step.scale) / 2) * 2);
      const h = isFixedSquare && step.scale === 1.0
        ? baseH
        : Math.max(48, Math.round((baseH * step.scale) / 2) * 2);

      const passMaxFrames = step.fps <= 8 ? Math.min(maxFrames, 36) : maxFrames;
      const timeline = selectFrameTimeline(
        sourceFrames,
        trimStartMs,
        trimEndMs,
        step.fps,
        passMaxFrames,
        speed
      );

      if (onProgress) {
        onProgress({
          pass: pass + 1,
          totalPasses: candidates.length,
          width: w,
          height: h,
          fps: step.fps,
          colors: step.colors,
          frames: timeline.frameIndices.length,
        });
      }

      const scaledFrames = resampleAndScaleFrames(sourceFrames, srcW, srcH, {
        width: w,
        height: h,
        crop: crop,
        frameIndices: timeline.frameIndices,
        delays: timeline.delays,
        fitPadding: fitPadding,
      });

      const bytes = encodeGif({
        width: w,
        height: h,
        frames: scaledFrames,
        maxColors: step.colors,
        dither: step.dither,
        deltaTolerance: step.tol,
      });

      const current = {
        bytes: bytes,
        width: w,
        height: h,
        fps: step.fps,
        colors: step.colors,
        frameCount: scaledFrames.length,
        pass: pass + 1,
        fitsTarget: targetBytes <= 0 || bytes.byteLength <= targetBytes,
      };

      if (!bestResult || bytes.byteLength < bestResult.bytes.byteLength) {
        bestResult = current;
      }

      if (current.fitsTarget) {
        return current;
      }
    }

    return bestResult;
  }

  root.GifCodec = {
    decodeGif: decodeGif,
    encodeGif: encodeGif,
    runSmartCompression: runSmartCompression,
  };
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : window);
