/**
 * Sentinel SDK for Node.js / Express
 * ────────────────────────────────────
 * 2 lines to add to any Node.js app:
 *   const sentinel = require('./sentinel_sdk/sentinel');
 *   sentinel.attach(app, { apiKey: 'GEMINI_KEY', ... });
 */

const https   = require("https");
const http    = require("http");
const { execSync } = require("child_process");
const nodemailer   = require_safe("nodemailer");

// ── safe optional require ─────────────────────────────────────────────────────
function require_safe(mod) {
  try { return require(mod); } catch { return null; }
}

// ── Dedup cache ───────────────────────────────────────────────────────────────
const _seen = new Map();
function isDup(key) {
  const now = Date.now();
  if (_seen.get(key) && now - _seen.get(key) < 60000) return true;
  _seen.set(key, now);
  return false;
}

// ── Terminal output ───────────────────────────────────────────────────────────
const C = {
  reset:"\x1b[0m", bold:"\x1b[1m", dim:"\x1b[2m",
  red:"\x1b[91m", green:"\x1b[92m", yellow:"\x1b[93m", cyan:"\x1b[96m"
};

function terminalDetected(event, appName) {
  const sev = (event.severity || "UNKNOWN").toUpperCase();
  const col = {CRITICAL:C.red,HIGH:C.yellow,MEDIUM:C.cyan,LOW:C.green}[sev] || C.cyan;
  console.log(`\n${C.bold}${C.red}${"━".repeat(60)}${C.reset}`);
  console.log(`${C.bold}🚨  SENTINEL — PROBLEM DETECTED  [${new Date().toISOString().slice(0,19).replace("T"," ")}]${C.reset}`);
  console.log(`${C.bold}${"━".repeat(60)}${C.reset}`);
  console.log(`  ${C.bold}App      :${C.reset} ${appName}`);
  console.log(`  ${C.bold}Severity :${C.reset} ${col}${sev}${C.reset}`);
  console.log(`  ${C.bold}Error    :${C.reset} ${String(event.error||"").slice(0,120)}`);
  if (event.path) console.log(`  ${C.bold}Path     :${C.reset} ${event.path}`);
  console.log(`${C.dim}  ⏳ Gemini AI diagnosing...${C.reset}`);
  console.log(`${C.bold}${"━".repeat(60)}${C.reset}\n`);
}

function terminalResolved(incident, appName) {
  const diag = incident.diagnosis || {};
  const fix  = incident.fix_result || {};
  const ok   = fix.success;
  const col  = ok ? C.green : C.yellow;
  const sev  = (diag.severity || "unknown").toUpperCase();
  const scol = {CRITICAL:C.red,HIGH:C.yellow,MEDIUM:C.cyan,LOW:C.green}[sev] || C.cyan;
  console.log(`\n${C.bold}${col}${"━".repeat(60)}${C.reset}`);
  console.log(`${C.bold}${ok?"✅":"⚠️ "}  SENTINEL — ${ok?"FIX APPLIED":"NEEDS ATTENTION"}${C.reset}`);
  console.log(`${C.bold}${col}${"━".repeat(60)}${C.reset}`);
  console.log(`  ${C.bold}Root Cause :${C.reset} ${diag.root_cause||"?"}`);
  console.log(`  ${C.bold}Confidence :${C.reset} ${C.cyan}${diag.confidence||0}%${C.reset}`);
  console.log(`  ${C.bold}Severity   :${C.reset} ${scol}${sev}${C.reset}`);
  console.log(`  ${C.bold}Action     :${C.reset} ${(fix.action_taken||fix.skipped_reason||"—").slice(0,120)}`);
  console.log(`\n  Status: ${ok ? C.green+"✅ AUTO-FIXED" : C.yellow+"⚠️  MANUAL ACTION NEEDED"}${C.reset}`);
  console.log(`${C.bold}${col}${"━".repeat(60)}${C.reset}\n`);
}

// ── Email ─────────────────────────────────────────────────────────────────────
async function sendEmail(opts, subject, text) {
  if (!opts.emailTo || !opts.smtpUser || !opts.smtpPass) return;
  const nm = require_safe("nodemailer");
  if (!nm) { console.log("[Sentinel] nodemailer not installed — npm install nodemailer"); return; }
  const t = nm.createTransport({
    host: opts.smtpHost || "smtp.gmail.com",
    port: opts.smtpPort || 587,
    secure: false,
    auth: { user: opts.smtpUser, pass: opts.smtpPass }
  });
  await t.sendMail({ from: opts.emailFrom || opts.smtpUser, to: opts.emailTo, subject, text });
}

// ── WhatsApp ──────────────────────────────────────────────────────────────────
async function sendWhatsApp(opts, body) {
  if (!opts.whatsappTo || !opts.twilioSid || !opts.twilioToken) return;
  const twilio = require_safe("twilio");
  if (!twilio) { console.log("[Sentinel] twilio not installed — npm install twilio"); return; }
  const client = twilio(opts.twilioSid, opts.twilioToken);
  await client.messages.create({
    from: opts.twilioFrom || "whatsapp:+14155238886",
    to:   opts.whatsappTo,
    body
  });
}

// ── AI Diagnosis (Gemini) ─────────────────────────────────────────────────────
async function diagnose(apiKey, ctx) {
  if (!apiKey) return ruleBasedDiagnosis(ctx);
  const prompt = `You are Sentinel SRE AI. Analyze this Node.js error and return ONLY valid JSON.
ERROR: ${JSON.stringify(ctx, null, 2)}
Return: {"root_cause":"...","confidence":88,"severity":"critical|high|medium|low","fix_type":"restart|clear_cache|dependency_fix|rate_limit|manual","fix_command":"shell cmd or null","explanation":"...","safe_to_autofix":true}`;

  return new Promise(resolve => {
    const body = JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] });
    const req = https.request({
      hostname: "generativelanguage.googleapis.com",
      path: `/v1beta/models/gemini-1.5-pro:generateContent?key=${apiKey}`,
      method: "POST", headers: { "Content-Type": "application/json" }
    }, res => {
      let data = "";
      res.on("data", c => data += c);
      res.on("end", () => {
        try {
          const p = JSON.parse(data);
          const text = p.candidates[0].content.parts[0].text.replace(/```json|```/g,"").trim();
          resolve(JSON.parse(text));
        } catch { resolve(ruleBasedDiagnosis(ctx)); }
      });
    });
    req.on("error", () => resolve(ruleBasedDiagnosis(ctx)));
    req.write(body); req.end();
  });
}

function ruleBasedDiagnosis(ctx) {
  const msg = (ctx.error || "").toLowerCase();
  const rules = [
    [["econnrefused","connection refused"],"DB/service connection refused","dependency_fix","npm install","high"],
    [["timeout","etimedout"],"Request timed out","rate_limit",null,"high"],
    [["heap out of memory","enomem"],"Memory exhausted","restart",null,"critical"],
    [["cannot find module","module not found"],"Missing npm package","dependency_fix","npm install","medium"],
    [["429","rate limit"],"Rate limit hit","rate_limit",null,"medium"],
  ];
  for (const [kws,root_cause,fix_type,fix_command,severity] of rules) {
    if (kws.some(k => msg.includes(k))) {
      return { root_cause, confidence:72, severity, fix_type, fix_command,
               explanation:"Rule-based match.", safe_to_autofix: fix_type==="dependency_fix" };
    }
  }
  return { root_cause:"Unknown error", confidence:30, severity:"medium",
           fix_type:"manual", fix_command:null, explanation:"Manual investigation needed.", safe_to_autofix:false };
}

function executeFix(diagnosis) {
  const { fix_type, fix_command, safe_to_autofix } = diagnosis;
  if (!safe_to_autofix) return { attempted:false, skipped_reason:"Unsafe — logged for manual review" };
  if (fix_type === "clear_cache") {
    Object.keys(require.cache).forEach(k => delete require.cache[k]);
    return { attempted:true, success:true, action_taken:"Module cache cleared" };
  }
  if (fix_command) {
    try {
      const out = execSync(fix_command, { timeout:30000 }).toString().slice(0,200);
      return { attempted:true, success:true, action_taken:`Ran: ${fix_command} → ${out}` };
    } catch(e) { return { attempted:true, success:false, action_taken:e.message.slice(0,200) }; }
  }
  return { attempted:false, skipped_reason:`No handler for '${fix_type}'` };
}

// ── Core process event handler ────────────────────────────────────────────────
async function processEvent(event, opts) {
  const appName = opts.appName || "MyApp";

  // STAGE 1 — immediate alerts
  terminalDetected(event, appName);
  sendEmail(opts, `[Sentinel 🚨] ${(event.severity||"").toUpperCase()} error in ${appName}`,
    `Error: ${event.error}\nPath: ${event.path||""}\nTime: ${event.timestamp}`).catch(()=>{});
  sendWhatsApp(opts,
    `🚨 *SENTINEL ALERT* — ${appName}\n━━━━━━━━━━━━━\n*Error*: ${String(event.error||"").slice(0,100)}\n⏳ _Diagnosing..._`
  ).catch(()=>{});

  // STAGE 2 — diagnose + fix
  const diagnosis  = await diagnose(opts.apiKey || "", event);
  const fix_result = executeFix(diagnosis);
  const incident   = { timestamp: event.timestamp, framework: event.framework,
                        error: event.error, diagnosis, fix_result };

  // STAGE 3 — post-fix alerts
  terminalResolved(incident, appName);
  const ok = fix_result.success;
  sendEmail(opts,
    `[Sentinel ${ok?"✅":"⚠️"}] ${ok?"Fixed":"Needs attention"}: ${diagnosis.root_cause.slice(0,60)}`,
    `Root Cause: ${diagnosis.root_cause}\nConfidence: ${diagnosis.confidence}%\nAction: ${fix_result.action_taken||fix_result.skipped_reason||"—"}\nStatus: ${ok?"✅ Auto-fixed":"⚠️ Manual action needed"}`
  ).catch(()=>{});
  sendWhatsApp(opts,
    `${ok?"✅":"⚠️"} *SENTINEL* — ${ok?"Fixed":"Needs Attention"}\n━━━━━━━━━━━━━\n*Cause*: ${diagnosis.root_cause.slice(0,80)}\n*Confidence*: ${diagnosis.confidence}%\n*Status*: ${ok?"✅ Auto-fixed":"⚠️ Manual fix needed"}`
  ).catch(()=>{});
}

// ── attach ────────────────────────────────────────────────────────────────────
function attach(app, options = {}) {
  const opts = options;

  // Global hooks
  process.on("uncaughtException", async err => {
    if (isDup(err.message)) return;
    await processEvent({ error: err.message, stack: err.stack, framework:"node",
                         timestamp: new Date().toISOString() }, opts);
  });
  process.on("unhandledRejection", async reason => {
    const msg = reason instanceof Error ? reason.message : String(reason);
    if (isDup(msg)) return;
    await processEvent({ error: msg, stack: reason?.stack, framework:"node",
                         timestamp: new Date().toISOString() }, opts);
  });

  // Express middleware
  if (app && typeof app.use === "function") {
    // Slow / 5xx detector
    app.use((req, res, next) => {
      const start = Date.now();
      res.on("finish", async () => {
        const ms = Date.now() - start;
        const key = `http:${req.path}:${res.statusCode}`;
        if ((res.statusCode >= 500 || ms > 5000) && !isDup(key)) {
          await processEvent({ error:`HTTP ${res.statusCode} ${req.method} ${req.path}`,
                               path:req.path, framework:"express",
                               timestamp:new Date().toISOString() }, opts);
        }
      });
      next();
    });
    // Error handler (must be 4-arg)
    app.use(async (err, req, res, next) => {
      const key = err.message + req.path;
      if (!isDup(key)) {
        await processEvent({ error:err.message, stack:err.stack, path:req.path,
                             framework:"express", timestamp:new Date().toISOString() }, opts);
      }
      res.status(500).json({ error:"Internal Server Error", sentinel:"investigating" });
    });

    console.log("\x1b[92m[Sentinel] ✅ Attached to Express — monitoring active\x1b[0m");
  }
}

module.exports = { attach };
