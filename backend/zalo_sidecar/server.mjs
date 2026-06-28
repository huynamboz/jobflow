/**
 * Zalo sidecar — holds one personal Zalo session (zca-js) and exposes a tiny
 * HTTP API the Django backend calls to deliver integration digests AND to drive
 * QR login from the admin UI (no CLI step needed).
 *
 *   GET  /health              → { ok, loggedIn }
 *   POST /send                → { threadId, threadType?, message }
 *   POST /login-qr/start      → begin QR login; returns current status
 *   GET  /login-qr/status     → { state, image?, user?, error?, loggedIn }
 *
 * Auth: shared secret in env ZALO_SIDECAR_TOKEN (header `x-sidecar-token`).
 * Session: persisted to creds.json so restarts don't need a re-scan.
 *
 *   PORT=3001 ZALO_SIDECAR_TOKEN=xxx npm start
 */
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import express from "express";
import { Zalo, ThreadType, LoginQRCallbackEventType as QR } from "zca-js";

const PORT = process.env.PORT || 3001;
const TOKEN = process.env.ZALO_SIDECAR_TOKEN || "";
const CREDS_PATH = new URL("./creds.json", import.meta.url);

let api = null; // logged-in zca-js API instance

// QR-login state machine, polled by the UI.
//   idle | waiting_scan | scanned | logged_in | expired | declined | error
let qr = { state: "idle", image: null, user: null, error: null };
let loginInProgress = false;

async function loginFromCreds() {
  let creds;
  try {
    creds = JSON.parse(readFileSync(CREDS_PATH, "utf8"));
  } catch {
    console.log("ℹ no creds.json yet — log in via the UI (or `npm run login`).");
    return;
  }
  try {
    api = await new Zalo().login(creds);
    qr.state = "logged_in";
    console.log("✅ Zalo session restored from creds.json.");
  } catch (e) {
    api = null;
    console.error("✗ Saved session invalid — re-login needed:", e?.message || e);
  }
}

function startQrLogin() {
  if (loginInProgress) return; // single listener per account
  loginInProgress = true;
  qr = { state: "starting", image: null, user: null, error: null };

  new Zalo()
    .loginQR({ language: "vi" }, (event) => {
      switch (event.type) {
        case QR.QRCodeGenerated:
          qr = { state: "waiting_scan", image: event.data.image, user: null, error: null };
          break;
        case QR.QRCodeScanned:
          qr.state = "scanned";
          qr.user = { name: event.data.display_name, avatar: event.data.avatar };
          break;
        case QR.QRCodeExpired:
          qr.state = "expired";
          break;
        case QR.QRCodeDeclined:
          qr.state = "declined";
          break;
        case QR.GotLoginInfo:
          // Persist so future restarts skip the QR scan.
          try {
            writeFileSync(
              CREDS_PATH,
              JSON.stringify(
                { cookie: event.data.cookie, imei: event.data.imei, userAgent: event.data.userAgent, language: "vi" },
                null,
                2,
              ),
            );
          } catch (e) {
            console.error("⚠ could not write creds.json:", e?.message || e);
          }
          break;
      }
    })
    .then((loggedInApi) => {
      api = loggedInApi;
      qr.state = "logged_in";
      console.log("✅ Zalo logged in via QR.");
    })
    .catch((e) => {
      qr = { state: "error", image: null, user: null, error: e?.message || String(e) };
      console.error("✗ QR login failed:", e?.message || e);
    })
    .finally(() => {
      loginInProgress = false;
    });
}

const threadTypeOf = (t) =>
  String(t || "user").toLowerCase() === "group" ? ThreadType.Group : ThreadType.User;

const app = express();
app.use(express.json({ limit: "1mb" }));

// Shared-secret gate (health is public).
app.use((req, res, next) => {
  if (req.path === "/health") return next();
  if (TOKEN && req.get("x-sidecar-token") !== TOKEN) {
    return res.status(401).json({ ok: false, error: "bad token" });
  }
  next();
});

app.get("/health", (_req, res) => res.json({ ok: true, loggedIn: !!api }));

app.post("/login-qr/start", (_req, res) => {
  if (api) return res.json({ state: "logged_in", loggedIn: true });
  startQrLogin();
  res.json({ ...qr, loggedIn: !!api });
});

app.get("/login-qr/status", (_req, res) => {
  res.json({ ...qr, loggedIn: !!api });
});

app.post("/logout", (_req, res) => {
  // Drop the session so a different account can log in via QR.
  api = null;
  loginInProgress = false;
  qr = { state: "idle", image: null, user: null, error: null };
  try {
    if (existsSync(CREDS_PATH)) rmSync(CREDS_PATH);
  } catch (e) {
    return res.status(500).json({ ok: false, error: e?.message || String(e) });
  }
  console.log("🔓 Zalo session cleared (creds.json removed).");
  res.json({ ok: true, loggedIn: false });
});

app.get("/threads", async (_req, res) => {
  if (!api) return res.status(503).json({ ok: false, error: "Zalo not logged in" });
  const out = { users: [], groups: [] };
  // Friends → direct-message threads.
  try {
    const friends = (await api.getAllFriends()) || [];
    out.users = friends.map((u) => ({
      id: u.userId,
      name: u.displayName || u.zaloName || u.userId,
      avatar: u.avatar || "",
    }));
  } catch (e) {
    out.usersError = e?.message || String(e);
  }
  // Groups → fetch IDs, then resolve names in one batch.
  try {
    const all = await api.getAllGroups();
    const ids = Object.keys(all?.gridVerMap || {});
    if (ids.length) {
      const info = await api.getGroupInfo(ids);
      const map = info?.gridInfoMap || {};
      out.groups = ids.map((id) => ({
        id,
        name: map[id]?.name || id,
        avatar: map[id]?.avt || "",
        members: map[id]?.totalMember || 0,
      }));
    }
  } catch (e) {
    out.groupsError = e?.message || String(e);
  }
  res.json({ ok: true, ...out });
});

app.post("/send", async (req, res) => {
  const { threadId, threadType, message } = req.body || {};
  if (!api) return res.status(503).json({ ok: false, error: "Zalo not logged in — đăng nhập QR trước." });
  if (!threadId || !message) {
    return res.status(400).json({ ok: false, error: "threadId and message are required" });
  }
  try {
    await api.sendMessage({ msg: String(message) }, String(threadId), threadTypeOf(threadType));
    res.json({ ok: true });
  } catch (e) {
    res.status(502).json({ ok: false, error: e?.message || String(e) });
  }
});

await loginFromCreds();
app.listen(PORT, () => console.log(`Zalo sidecar listening on :${PORT}`));
