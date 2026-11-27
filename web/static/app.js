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
  const convertOverlay = document.getElementById("convertOverlay");
  const convertStatus = document.getElementById("convertStatus");
  const convertProgress = document.getElementById("convertProgress");
  const convertProgressBar = document.getElementById("convertProgressBar");
  const convertEta = document.getElementById("convertEta");
  const convertFallback = document.getElementById("convertFallback");
  const convertHide = document.getElementById("convertHide");

  if (convertButton) {
    const label = convertButton.querySelector("strong");
    const sublabel = convertButton.querySelector("small");
    const originalLabel = label ? label.textContent : "";
    const originalSublabel = sublabel ? sublabel.textContent : "";
    const originalHint = convertHint ? convertHint.textContent : "";
    const startUrl = convertButton.dataset.startUrl || convertButton.href;
    const mp4Url = convertButton.dataset.mp4Url || "";

    if (mp4Url && convertFallback) {
      convertFallback.href = mp4Url;
    }

    let pollTimer = 0;
    let startedAt = 0;

    const setProgress = (value) => {
      const pct = Math.max(0, Math.min(100, Math.round(value)));
      if (convertProgressBar) convertProgressBar.style.width = `${pct}%`;
      if (convertProgress) {
        convertProgress.setAttribute("aria-valuenow", String(pct));
      }
    };

    const setStage = (stage, progress) => {
      if (convertStatus && stage) convertStatus.textContent = stage;
      if (typeof progress === "number") setProgress(progress);
      if (convertEta && startedAt) {
        const elapsed = Math.round((Date.now() - startedAt) / 1000);
        convertEta.textContent = `${elapsed}s elapsed`;
      }
    };

    const stopPolling = () => {
      if (pollTimer) window.clearTimeout(pollTimer);
      pollTimer = 0;
    };

    const resetButton = () => {
      delete convertButton.dataset.busy;
      convertButton.classList.remove("is-busy");
      convertButton.removeAttribute("aria-busy");
      if (label) label.textContent = originalLabel;
      if (sublabel) sublabel.textContent = originalSublabel;
      if (convertHint) convertHint.textContent = originalHint;
    };

    const fail = (message) => {
      stopPolling();
      resetButton();
      if (convertStatus) convertStatus.textContent = message;
      if (convertEta) convertEta.textContent = "";
      setProgress(100);
      notify(message);
    };

    const poll = (jobId) => {
      window.clearTimeout(pollTimer);
      pollTimer = window.setTimeout(async () => {
        try {
          const response = await fetch(`/convert/status/${jobId}`, {
            headers: { Accept: "application/json" },
            cache: "no-store",
          });
          if (response.status === 404) {
            fail("That conversion expired. Please try again.");
            return;
          }
          if (!response.ok) {
            throw new Error(`status ${response.status}`);
          }
          const data = await response.json();
          setStage(data.stage, data.progress);
          if (data.status === "done" && data.download_url) {
            stopPolling();
            setProgress(100);
            if (convertStatus) {
              convertStatus.textContent = "Ready! Starting your download...";
            }
            window.location.href = data.download_url;
            window.setTimeout(() => {
              if (convertOverlay) convertOverlay.hidden = true;
              resetButton();
            }, 1800);
            return;
          }
          if (data.status === "failed") {
            fail(data.error || "Conversion failed. Try the MP4 download instead.");
            return;
          }
          poll(jobId);
        } catch {
          fail("Lost contact with the converter. Try the MP4 download.");
        }
      }, 900);
    };

    const openOverlay = () => {
      startedAt = Date.now();
      setProgress(2);
      if (convertStatus) convertStatus.textContent = "Queuing conversion...";
      if (convertEta) convertEta.textContent = "0s elapsed";
      if (convertOverlay) convertOverlay.hidden = false;
    };

    convertButton.addEventListener("click", async (event) => {
      if (convertButton.dataset.busy === "1") {
        event.preventDefault();
        return;
      }

      event.preventDefault();
      convertButton.dataset.busy = "1";
      convertButton.classList.add("is-busy");
      convertButton.setAttribute("aria-busy", "true");
      if (label) label.textContent = "Converting...";
      if (sublabel) sublabel.textContent = "Hang tight, this can take a moment";
      if (convertHint) {
        convertHint.textContent =
          "Converting on the server. The download starts automatically when it is ready.";
      }
      openOverlay();

      try {
        const response = await fetch(startUrl, {
          headers: { Accept: "application/json" },
          cache: "no-store",
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          fail(
            data.detail ||
              "Could not start the conversion. Try the MP4 download."
          );
          return;
        }
        if (data.status === "done" && data.download_url) {
          window.location.href = data.download_url;
          window.setTimeout(() => {
            if (convertOverlay) convertOverlay.hidden = true;
            resetButton();
          }, 1800);
          return;
        }
        if (data.id) {
          setStage(data.stage, data.progress);
          poll(data.id);
        } else {
          fail("Could not start the conversion. Try the MP4 download.");
        }
      } catch {
        fail("Could not reach the converter. Try the MP4 download.");
      }
    });

    if (convertHide) {
      convertHide.addEventListener("click", () => {
        stopPolling();
        if (convertOverlay) convertOverlay.hidden = true;
        resetButton();
      });
    }
  }
})();
