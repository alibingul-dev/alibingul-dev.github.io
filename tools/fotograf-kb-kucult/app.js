// Photo -> JPEG under a target size. Runs entirely in the browser.
(function () {
  var T = window.T;
  var HEIC_LIB = "https://cdn.jsdelivr.net/npm/heic2any@0.0.4/dist/heic2any.min.js";

  var el = {
    drop: document.getElementById("drop"),
    presets: document.getElementById("presets"),
    kb: document.getElementById("kb"),
    side: document.getElementById("side"),
    result: document.getElementById("result"),
    preview: document.getElementById("preview"),
    dl: document.getElementById("dl")
  };

  var current = { file: null, img: null, out: null };
  var runId = 0;

  function isHeic(f) {
    return /image\/hei[cf]/i.test(f.type) || /\.hei[cf]$/i.test(f.name);
  }

  function loadScript(src) {
    return new Promise(function (res, rej) {
      if (window.heic2any) return res();
      var s = document.createElement("script");
      s.src = src; s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    });
  }

  function blobToImage(blob) {
    return new Promise(function (res, rej) {
      var url = URL.createObjectURL(blob);
      var img = new Image();
      img.onload = function () { res(img); };
      img.onerror = function () { URL.revokeObjectURL(url); rej(new Error("decode")); };
      img.src = url;
    });
  }

  function toBlob(canvas, q) {
    return new Promise(function (res) { canvas.toBlob(res, "image/jpeg", q); });
  }

  function draw(img, scale) {
    var w = Math.max(1, Math.round(img.naturalWidth * scale));
    var h = Math.max(1, Math.round(img.naturalHeight * scale));
    var c = document.createElement("canvas");
    c.width = w; c.height = h;
    var ctx = c.getContext("2d");
    ctx.fillStyle = "#fff";               // transparent PNG -> white, not black
    ctx.fillRect(0, 0, w, h);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, 0, 0, w, h);
    return c;
  }

  // Highest JPEG quality that fits; shrinks dimensions only when quality floor is not enough.
  async function compress(img, targetBytes, maxSide) {
    var longSide = Math.max(img.naturalWidth, img.naturalHeight);
    var scale = maxSide && longSide > maxSide ? maxSide / longSide : 1;
    var Q_MIN = 0.3, Q_MAX = 0.92;

    for (var pass = 0; pass < 14; pass++) {
      var c = draw(img, scale);
      var top = await toBlob(c, Q_MAX);
      if (top.size <= targetBytes) return { blob: top, w: c.width, h: c.height, q: Q_MAX };

      var low = await toBlob(c, Q_MIN);
      if (low.size <= targetBytes) {
        var lo = Q_MIN, hi = Q_MAX, best = low;
        for (var i = 0; i < 7; i++) {
          var mid = (lo + hi) / 2;
          var b = await toBlob(c, mid);
          if (b.size <= targetBytes) { best = b; lo = mid; } else { hi = mid; }
        }
        return { blob: best, w: c.width, h: c.height, q: lo };
      }

      var factor = Math.sqrt(targetBytes / low.size) * 0.95;
      scale *= Math.min(factor, 0.9);
      if (c.width < 40 || c.height < 40) break;
    }
    return null;
  }

  function targetBytes() {
    var kb = parseFloat(el.kb.value);
    return kb > 0 ? Math.floor(kb * 1000) : 0;  // 1 KB = 1000 B: also passes portals that count 1024
  }

  function setActivePreset() {
    Array.prototype.forEach.call(el.presets.querySelectorAll("button"), function (b) {
      b.classList.toggle("on", b.dataset.kb === String(el.kb.value));
    });
  }

  function show(html) { el.result.innerHTML = html; }

  async function run() {
    if (!current.img) return;
    var id = ++runId;
    var tb = targetBytes();
    if (!tb) { show('<span class="err">' + T.badKb + "</span>"); return; }
    show(T.working);
    el.dl.disabled = true;

    var out = await compress(current.img, tb, parseInt(el.side.value, 10) || 0);
    if (id !== runId) return;
    if (!out) { show('<span class="err">' + T.tooSmall + "</span>"); return; }

    current.out = out;
    if (el.preview.src) URL.revokeObjectURL(el.preview.src);
    el.preview.src = URL.createObjectURL(out.blob);
    el.preview.hidden = false;
    el.dl.disabled = false;

    var resized = out.w !== current.img.naturalWidth;
    show(
      '<span class="ok">' + T.done + "</span> " +
      '<span class="mono">' + Tool.formatBytes(current.file.size) + " → " +
      (out.blob.size / 1000).toFixed(1) + " KB</span><br>" +
      '<span class="mono">' + out.w + "×" + out.h + " px · " + T.quality + " %" + Math.round(out.q * 100) + "</span>" +
      (resized ? "<br><small>" + T.resized + "</small>" : "")
    );
  }

  async function onFiles(files) {
    var f = files[0];
    current = { file: f, img: null, out: null };
    el.preview.hidden = true;
    el.dl.disabled = true;
    show(T.reading);
    try {
      var blob = f;
      if (isHeic(f)) {
        await loadScript(HEIC_LIB);
        var conv = await window.heic2any({ blob: f, toType: "image/jpeg", quality: 0.95 });
        blob = Array.isArray(conv) ? conv[0] : conv;
      }
      current.img = await blobToImage(blob);
    } catch (e) {
      show('<span class="err">' + T.cantRead + "</span>");
      return;
    }
    run();
  }

  Tool.dropZone(el.drop, onFiles);

  el.presets.addEventListener("click", function (e) {
    var b = e.target.closest("button");
    if (!b) return;
    el.kb.value = b.dataset.kb;
    setActivePreset();
    run();
  });
  el.kb.addEventListener("change", function () { setActivePreset(); run(); });
  el.side.addEventListener("change", run);

  el.dl.addEventListener("click", function () {
    if (!current.out) return;
    var base = current.file.name.replace(/\.[^.]+$/, "") || "foto";
    Tool.download(current.out.blob, base + "_" + el.kb.value + "kb.jpg");
  });

  setActivePreset();
})();
