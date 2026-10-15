// Shared runtime for every tool under /tools/.
// Fill CONFIG once; every tool picks it up. Empty value = feature off.
(function () {
  var CONFIG = {
    goatcounter: "",   // e.g. "https://alibingul.goatcounter.com/count" (cookieless analytics)
    newsletterAction: "", // e.g. Buttondown/MailerLite form action URL
    ads: false          // true only once an ad network is approved
  };

  if (CONFIG.goatcounter) {
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://gc.zgo.at/count.js";
    s.setAttribute("data-goatcounter", CONFIG.goatcounter);
    document.head.appendChild(s);
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (CONFIG.ads) document.body.classList.add("ads-on");
    if (CONFIG.newsletterAction) {
      document.body.classList.add("notify-on");
      var f = document.querySelector(".notify form");
      if (f) f.action = CONFIG.newsletterAction;
    }
    var y = document.getElementById("year");
    if (y) y.textContent = new Date().getFullYear();
  });

  // Small helpers file tools reuse.
  window.Tool = {
    formatBytes: function (n) {
      if (n < 1024) return n + " B";
      if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
      return (n / 1048576).toFixed(2) + " MB";
    },
    download: function (blob, name) {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    },
    // Wires a .drop zone: click or drag-drop, calls onFiles(FileList).
    dropZone: function (el, onFiles) {
      var input = el.querySelector("input[type=file]");
      el.addEventListener("click", function () { input.click(); });
      input.addEventListener("change", function () { if (input.files.length) onFiles(input.files); });
      ["dragenter", "dragover"].forEach(function (e) {
        el.addEventListener(e, function (ev) { ev.preventDefault(); el.classList.add("over"); });
      });
      ["dragleave", "drop"].forEach(function (e) {
        el.addEventListener(e, function (ev) { ev.preventDefault(); el.classList.remove("over"); });
      });
      el.addEventListener("drop", function (ev) {
        if (ev.dataTransfer.files.length) onFiles(ev.dataTransfer.files);
      });
    }
  };
})();
