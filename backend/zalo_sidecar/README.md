# Zalo sidecar (zca-js)

A tiny Node service that holds **one personal Zalo session** (via
[zca-js](https://github.com/RFS-ADRENO/zca-js)) and lets the Django backend
send integration digests to a Zalo user/group.

> zca-js automates a personal account (not the official OA API). It simulates
> browser behaviour and carries an account-suspension risk — use a dedicated
> Zalo account for sending.

## Setup

```bash
cd backend/zalo_sidecar
npm install
ZALO_SIDECAR_TOKEN=<shared-secret> PORT=3001 npm start
```

Then **log in from the admin UI**: Integrations → Zalo → **Đăng nhập QR** →
scan with the sender account's Zalo app. The session is saved to `creds.json`,
so restarts don't need a re-scan.

> CLI alternative (headless servers): `npm run login` writes `creds.json` the
> same way before `npm start`.

Then in `backend/.env`:

```
ZALO_SIDECAR_URL=http://localhost:3001
ZALO_SIDECAR_TOKEN=<same shared-secret>
```

## Finding a threadId (recipient)

The `recipient` you enter in the JobFlow "Connect Zalo" modal is a Zalo
**threadId** — a user ID (someone the sender account can message) or a group ID.
Run the listener once and message the sender account to see incoming `threadId`s,
or use a known group ID. Set `thread_type` to `user` or `group` accordingly.

## API

| Method | Path      | Body                                           |
| ------ | --------- | ---------------------------------------------- |
| GET    | `/health` | → `{ ok, loggedIn }`                            |
| POST   | `/send`   | `{ threadId, threadType?, message }` (+ token) |

`threadType`: `"user"` (default) or `"group"`. Auth header: `x-sidecar-token`.
