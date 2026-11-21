(() => {
  "use strict";

  const toast = document.getElementById("toast");
  let toastTimer = 0;

  function notify(message) {
    if (!toast) return;
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => {
      toast.classList.remove("is-visible");
    }, 4200);
  }

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const url = window.location.href;
      try {
        await navigator.clipboard.writeText(url);
        notify("Page link copied.");
      } catch {
        window.prompt("Copy this page link:", url);
      }
    });
  });

  const resolveForm = document.querySelector("[data-resolve-form]");

  if (resolveForm) {
    const submit = resolveForm.querySelector('button[type="submit"]');
    const label = submit ? submit.querySelector(".resolve-submit-label") : null;
    const originalLabel = label ? label.textContent : "";

    resolveForm.addEventListener("submit", () => {
      if (!submit) return;
      submit.dataset.busy = "1";
      submit.setAttribute("aria-busy", "true");
      submit.disabled = true;
      if (label) label.textContent = "Finding GIF...";
    });

    window.addEventListener("pageshow", () => {
      if (!submit) return;
      delete submit.dataset.busy;
      submit.removeAttribute("aria-busy");
      submit.disabled = false;
      if (label) label.textContent = originalLabel;
    });
  }

  const convertButton = document.getElementById("convertBtn");
  const convertHint = document.getElementById("convertHint");

  if (convertButton) {
    const label = convertButton.querySelector("strong");
    const sublabel = convertButton.querySelector("small");
    const originalLabel = label ? label.textContent : "";
    const originalSublabel = sublabel ? sublabel.textContent : "";
    const originalHint = convertHint ? convertHint.textContent : "";
    const waitMs = Number(convertButton.dataset.waitMs) || 120000;

    convertButton.addEventListener("click", (event) => {
      if (convertButton.dataset.busy === "1") {
        event.preventDefault();
        return;
      }

      convertButton.dataset.busy = "1";
      convertButton.classList.add("is-busy");
      convertButton.setAttribute("aria-busy", "true");

      if (label) label.textContent = "Converting...";
      if (sublabel) sublabel.textContent = "Your download will start automatically";
      if (convertHint) {
        convertHint.textContent =
          "Converting on the server. This can take up to a minute for large files.";
      }

      notify("Converting to GIF. Your download will start automatically.");

      window.setTimeout(() => {
        delete convertButton.dataset.busy;
        convertButton.classList.remove("is-busy");
        convertButton.removeAttribute("aria-busy");
        if (label) label.textContent = originalLabel;
        if (sublabel) sublabel.textContent = originalSublabel;
        if (convertHint) convertHint.textContent = originalHint;
      }, waitMs);
    });
  }

  const video = document.querySelector("[data-preview-video]");
  const fallback = document.querySelector("[data-video-fallback]");

  if (video && fallback) {
    const showFallback = () => {
      video.hidden = true;
      fallback.hidden = false;
    };

    video.addEventListener("error", showFallback);
    window.setTimeout(() => {
      if (video.error) showFallback();
    }, 7000);
  }
})();
