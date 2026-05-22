/**
 * Sentinel Browser SDK
 * Add this ONE script tag to any HTML page to monitor frontend JS errors.
 *
 * Usage:
 *   <script src="sentinel.browser.js" data-key="YOUR_GEMINI_KEY"></script>
 */

(function () {
  const script  = document.currentScript;
  const apiKey  = script ? script.getAttribute("data-key") : "";
  const endpoint = script ? script.getAttribute("data-endpoint") : "";  // optional: your backend /sentinel/report

  const _seen = {};
  function isDup(key) {
    const now = Date.now();
    if (_seen[key] && now - _seen[key] < 30000) return true;
    _seen[key] = now;
    return false;
  }

  function report(errorData) {
    const key = errorData.message + (errorData.source || "");
    if (isDup(key)) return;

    const payload = {
      ...errorData,
      url:       location.href,
      userAgent: navigator.userAgent,
      timestamp: new Date().toISOString(),
      framework: "browser",
    };

    // Send to your backend if endpoint provided
    if (endpoint) {
      fetch(endpoint, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(payload),
        keepalive: true,
      }).catch(() => {});
    }

    // Log to console in dev
    if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
      console.groupCollapsed(`[Sentinel] 🛡️ Error captured: ${errorData.message}`);
      console.log(payload);
      console.groupEnd();
    }
  }

  // ── Hook into all browser error types ──────────────────────────────────────

  window.addEventListener("error", (e) => {
    report({
      type:    "js_error",
      message: e.message,
      source:  e.filename,
      line:    e.lineno,
      col:     e.colno,
      stack:   e.error?.stack,
    });
  });

  window.addEventListener("unhandledrejection", (e) => {
    const msg = e.reason instanceof Error ? e.reason.message : String(e.reason);
    report({
      type:    "unhandled_promise",
      message: msg,
      stack:   e.reason?.stack,
    });
  });

  // Patch fetch to catch failed requests
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    try {
      const res = await origFetch(...args);
      if (res.status >= 500) {
        report({
          type:    "fetch_error",
          message: `HTTP ${res.status} on ${args[0]}`,
          url:     args[0],
          status:  res.status,
        });
      }
      return res;
    } catch (err) {
      report({ type: "fetch_failed", message: err.message, url: args[0] });
      throw err;
    }
  };

  // Patch XMLHttpRequest
  const origOpen  = XMLHttpRequest.prototype.open;
  const origSend  = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this._sentinelUrl = url;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener("load", function () {
      if (this.status >= 500) {
        report({
          type:    "xhr_error",
          message: `HTTP ${this.status} on ${this._sentinelUrl}`,
          url:     this._sentinelUrl,
          status:  this.status,
        });
      }
    });
    return origSend.apply(this, arguments);
  };

  console.log("[Sentinel] 🛡️ Browser monitoring active");
})();
