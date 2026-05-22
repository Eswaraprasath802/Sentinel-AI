/**
 * Sentinel Browser SDK
 * Add one script tag to any HTML page
 * <script src="sentinel.browser.js" data-url="http://localhost:8000" data-app="MyApp"></script>
 */
(function () {
    const script  = document.currentScript;
    const SERVER  = (script && script.dataset.url) || "http://localhost:8000";
    const APP     = (script && script.dataset.app) || "BrowserApp";

    function report(error, source, lineno, colno, errorObj) {
        const payload = {
            app_name:   APP,
            language:   "javascript",
            framework:  "browser",
            error:      error || "Unknown JS error",
            error_type: errorObj ? errorObj.name : "Error",
            traceback:  errorObj ? errorObj.stack : `${source}:${lineno}:${colno}`,
            endpoint:   window.location.pathname,
            method:     "GET",
            timestamp:  new Date().toISOString()
        };
        navigator.sendBeacon(SERVER + "/report", JSON.stringify(payload));
    }

    // Catch all JS errors
    window.onerror = function (message, source, lineno, colno, error) {
        report(message, source, lineno, colno, error);
        return false;
    };

    // Catch unhandled promise rejections
    window.addEventListener("unhandledrejection", function (e) {
        report(String(e.reason), window.location.href, 0, 0, e.reason);
    });

    console.log("[Sentinel] Browser monitoring active →", SERVER);
})();
