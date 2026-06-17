/**
 * One-time QR login. Run once to capture a Zalo session:
 *
 *     cd backend/zalo_sidecar && npm install && npm run login
 *
 * Scan the QR (printed to ./qr.png) with the Zalo app on the phone whose
 * account will SEND the digests. On success the cookie/imei/userAgent are
 * written to creds.json — which server.mjs then loads. Re-run if the session
 * expires (Zalo logs out, password change, etc.).
 */
import { writeFileSync } from "node:fs";
import { Zalo } from "zca-js";

const CREDS_PATH = new URL("./creds.json", import.meta.url);

console.log("Opening Zalo QR login… a qr.png will be written to this folder.");

const zalo = new Zalo();
await zalo.loginQR(
  { qrPath: "./qr.png", language: "vi" },
  (data) => {
    // Fired once the QR is generated, then again with the session payload.
    if (data?.cookie && data?.imei && data?.userAgent) {
      writeFileSync(
        CREDS_PATH,
        JSON.stringify(
          { cookie: data.cookie, imei: data.imei, userAgent: data.userAgent, language: "vi" },
          null,
          2,
        ),
      );
      console.log("✅ Saved session to creds.json — you can now run `npm start`.");
    }
  },
);

// loginQR resolves after a successful scan; give the callback a tick to flush.
setTimeout(() => process.exit(0), 1000);
