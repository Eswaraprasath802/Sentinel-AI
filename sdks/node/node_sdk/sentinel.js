/**
 * Sentinel Node.js SDK
 * Works with Express, Next.js, any Node.js app
 * Reports errors to the Sentinel Agent Server
 */

const http  = require("http");
const https = require("https");
const url   = require("url");

class Sentinel {
    constructor(options = {}) {
        this.serverUrl = options.serverUrl || process.env.SENTINEL_URL || "http://localhost:8000";
        this.appName   = options.appName   || process.env.SENTINEL_APP || "NodeApp";
        this.framework = options.framework || "express";
        this.language  = "node";
        this._checkHealth();
    }

    // ── Attach to Express app ─────────────────────────────────────
    attach(app) {
        const self = this;

        // Catch all unhandled errors
        app.use((err, req, res, next) => {
            self.report({
                error:     err.message,
                error_type:err.name || "Error",
                traceback: err.stack || "",
                endpoint:  req.path,
                method:    req.method,
            });
            res.status(500).json({
                error:    "Internal Server Error",
                sentinel: "investigating"
            });
        });

        // Catch global unhandled promise rejections
        process.on("unhandledRejection", (reason) => {
            self.report({
                error:      String(reason),
                error_type: "UnhandledRejection",
                traceback:  reason?.stack || "",
                endpoint:   "background",
                method:     "ASYNC",
            });
        });

        console.log(`\x1b[32m[Sentinel] ✅ Attached to ${this.framework} — monitoring active\x1b[0m`);
        return app;
    }

    // ── Manually report an error ──────────────────────────────────
    report(errorData = {}) {
        const payload = {
            app_name:   this.appName,
            language:   this.language,
            framework:  this.framework,
            error:      errorData.error      || "Unknown error",
            error_type: errorData.error_type || "Error",
            traceback:  errorData.traceback  || "",
            endpoint:   errorData.endpoint   || "unknown",
            method:     errorData.method     || "unknown",
            timestamp:  new Date().toISOString(),
        };
        this._post("/report", payload);
    }

    // ── Fire and forget HTTP POST ─────────────────────────────────
    _post(path, payload) {
        try {
            const body    = JSON.stringify(payload);
            const parsed  = url.parse(this.serverUrl);
            const lib     = parsed.protocol === "https:" ? https : http;
            const options = {
                hostname: parsed.hostname,
                port:     parsed.port || (parsed.protocol === "https:" ? 443 : 80),
                path:     path,
                method:   "POST",
                headers: {
                    "Content-Type":   "application/json",
                    "Content-Length": Buffer.byteLength(body)
                },
                timeout: 3000
            };
            const req = lib.request(options);
            req.on("error", () => {});  // silent fail
            req.write(body);
            req.end();
        } catch (e) {}
    }

    _checkHealth() {
        try {
            const parsed = url.parse(this.serverUrl + "/health");
            const lib    = parsed.protocol === "https:" ? https : http;
            lib.get(this.serverUrl + "/health", (res) => {
                if (res.statusCode === 200) {
                    console.log(`\x1b[32m[Sentinel] ✅ Agent Server connected\x1b[0m`);
                } else {
                    console.log(`\x1b[33m[Sentinel] ⚠️  Agent Server not reachable\x1b[0m`);
                }
            }).on("error", () => {
                console.log(`\x1b[33m[Sentinel] ⚠️  Agent Server not reachable at ${this.serverUrl}\x1b[0m`);
            });
        } catch(e) {}
    }
}

module.exports = Sentinel;
