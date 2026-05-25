/**
 * Express Example — Sentinel Node SDK
 */

const express  = require("express");
const Sentinel = require("../../sdks/node/node_sdk/sentinel");

const app = express();

// ── 2 Lines ───────────────────────────────────────────────────────
const sentinel = new Sentinel({ appName: "ExpressDemo", framework: "express" });
sentinel.attach(app);
// ─────────────────────────────────────────────────────────────────

app.get("/", (req, res) => res.json({ status: "running" }));

app.get("/crash", (req, res, next) => {
    next(new Error("ECONNREFUSED: DB connection refused on port 5432"));
});

app.listen(3000, () => console.log("Express running on port 3000"));
