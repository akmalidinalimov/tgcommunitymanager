# Media & Stack — Implementation-Ready Findings

Scope: media generation providers (Higgsfield / kie.ai / fal.ai / Replicate / Segmind) and the production Python stack for an Uzbek-language AI-education Telegram channel (3000+ members, linked discussion group, posts at 10:00 and 21:00 Asia/Tashkent, Hostinger KVM VPS + Postgres, $50–150/mo).

---

## 1. Higgsfield API — implementation-ready

### 1.1 Hosts, credentials, auth
| Item | Value |
|---|---|
| API base URL | `https://platform.higgsfield.ai` |
| Dashboard / credential creation | `https://cloud.higgsfield.ai` (Clerk auth; redirects to `https://cloud.higgsfield.ai/sign-in?redirect_url=.../dashboard`) |
| Docs | `https://docs.higgsfield.ai/docs/` — page index at `https://docs.higgsfield.ai/docs/llms.txt` (20 pages) |
| OpenAPI 3.1 spec | `https://docs.higgsfield.ai/docs/openapi.json` — spec `version: 2.0.0`, ~104 KB |
| Auth header | `Authorization: Key <KEY_ID>:<KEY_SECRET>` |
| Legacy headers | `hf-api-key` + `hf-secret` — still accepted, deprecated for new integrations |
| Live probe | Unauthenticated `POST https://platform.higgsfield.ai/higgsfield-ai/soul/standard` → HTTP 401 `{"detail":"Invalid credentials"}` (verified live) |
| Correlation | Every response carries an `X-Correlation-ID` header — persist alongside `request_id` for support tickets |
| Support | `support@higgsfield.ai` (also the rate-limit escalation path; invoice billing for enterprise) |

Credentials cannot be created without a `cloud.higgsfield.ai` account. There is **no public page** listing API credit prices, model catalog access, or numeric rate limits — the docs say to "view the limits assigned to your account in Higgsfield Cloud."

### 1.2 SDKs
- Python: `pip install higgsfield-client` — repo `github.com/higgsfield-ai/higgsfield-client`
- Node: `npm install @higgsfield/client` — repo `github.com/higgsfield-ai/higgsfield-js`
- Python API surface: `higgsfield_client.subscribe(model, arguments={...})`, `subscribe_async`, `submit(model, arguments=..., webhook_url='https://...')`, `submit_async`; request controller with `poll_request_status()` yielding `Queued` / `InProgress` / `Completed` / `Failed` / `NSFW` / `Cancelled` objects, each with `.get()`; helpers `upload`, `upload_file`, `upload_image`.
- Env vars: `HF_KEY="key:secret"` **or** `HF_API_KEY` + `HF_API_SECRET`. (TS client uses `HF_CREDENTIALS`.)
- `submit(webhook_url=...)` is the clean way to set the webhook — avoids hand-encoding the `hf_webhook` query param.

### 1.3 Async flow (exact)
1. `POST https://platform.higgsfield.ai/<model-path>` → HTTP **200** immediately:
```json
{"status":"queued","request_id":"<uuid>",
 "status_url":"https://platform.higgsfield.ai/requests/<id>/status",
 "cancel_url":"https://platform.higgsfield.ai/requests/<id>/cancel"}
```
2. `GET /requests/{request_id}/status` → `RequestStatus` schema. Required fields: `status`, `request_id`. Other fields: `status_url`, `cancel_url`, `error` (string|null), `images[]`, `video`, `audio`, `audios[]` — each a `MediaOutput` with a `url`. Some video/3D ops also return `zip`, `mov`, `jsx`, `fbx`, `ply`.
3. Non-terminal statuses: `queued`, `in_progress`. Terminal: `completed`, `failed`, `nsfw`, `canceled`.
4. `POST /requests/{request_id}/cancel` → **202 Accepted**, empty body — only while *every* job is still `queued`; **400** once processing started.

Only two request-management paths exist: `GET /requests/{request_id}/status` and `POST /requests/{request_id}/cancel`.

### 1.4 Polling curve (official, adopt as house standard)
Source: `https://docs.higgsfield.ai/docs/concepts/polling.md` (ships a full Python `httpx` example).
- initial interval **2.0 s**, multiplier **×1.5**, cap **10.0 s**, random jitter up to **+0.5 s**
- stop on `{completed, failed, nsfw, canceled}`; enforce an app-level timeout (use 10–15 min, per kie.ai's guidance)
- retry rules: `200` + non-terminal → keep polling; `401` → stop, fix credentials; `404` → stop; `5xx` / network → retry with backoff

### 1.5 Webhooks
- Set via **URL-encoded QUERY parameter** `hf_webhook` on the generation POST, e.g. `?hf_webhook=https%3A%2F%2Fexample.com%2Fwebhooks%2Fhiggsfield`. It is a query param, **not** a body field, and it does **not** appear in `openapi.json` (model POST operations have `parameters: null`).
- Payload envelope: `{request_id, status, error, payload}` where `payload` = `{images:[{url, content_type}]}` or `{video:{url, content_type}}` or `{audio:...}`.
  - `failed` → `error:"Generation failed"`, `payload:null`
  - `nsfw` → `error:null`, `payload:null`
- Endpoint must respond within **10 seconds**. 5xx/network retried up to **2 hours**; 4xx = permanent, no retry.
- Duplicate deliveries possible → dedupe on `request_id` + terminal status.
- **No documented signature or shared secret.** Treat the callback as an untrusted hint: use an unguessable path segment and re-read the authenticated `status_url` before acting.

### 1.6 Errors, idempotency, concurrency
- **No idempotency key.** Docs verbatim: "Do not automatically repeat a generation POST after an ambiguous timeout because submissions do not currently accept an idempotency key." → persist `request_id` in the same Postgres transaction as the submit; never blind-retry a POST (double-charges credits).
- `403` = "Insufficient credits" — retry only "After funding the account."
- `404` = "Request or model not found **for this account**" — model availability is entitlement-gated, so a funded account may still 404 on models its plan lacks. Docs also note an unavailable model can return `404`, `423`, or `503`.
- Rate limiting is **concurrency-based**, per account / subscription / model. Exceeding returns HTTP **400** (not 429) with `{"detail":"Maximum number of concurrent requests (4) has been reached"}`. **No** `X-RateLimit-*` headers, **no** `Retry-After`. → gate submissions with a semaphore; a generic "4xx = permanent failure" handler will silently drop jobs.

### 1.7 Retention & file uploads
- Output retention: **at least 7 days** — "Generated output is accessible for at least seven days after creation and may be removed after that period." FAQ: "a minimum of 7 days from the time of creation."
- Billing edge cases: failed / nsfw-moderated / successfully-canceled requests are **not charged**; reserved credits auto-refunded.
- Credits expire **one year** after being added to the balance. (Third-party blogs claiming 90-day expiry are describing the consumer app or are stale — dropped.)
- Input uploads: `POST https://platform.higgsfield.ai/files/generate-upload-url` body `{"content_type":"image/jpeg"}` → `{public_url, upload_url, content_type, upload_headers{Content-Type, x-amz-tagging: retention=temporary}}`. Presigned URL expires after **1 hour**.
- Accepted upload types: `image/jpeg`, `image/jpg`, `image/png`, `image/webp`, `image/gif`, `audio/wav`, `audio/x-wav`, `video/mp4`.

### 1.8 Model endpoints and request bodies
Catalog counted by the researcher as 50 paths / 48 model endpoints; the verifier's independent parse returned 28 and was self-assessed as unreliable (likely truncation). **Do not hardcode the count.** Re-download `openapi.json` on the VPS and assert `len(spec['paths'])` as a deploy-time runtime check; the vendor self-reports spec version 2.0.0 and the catalog changes fast.

Image model paths: `/higgsfield-ai/soul/standard`, `/higgsfield-ai/soul/character`, `/higgsfield-ai/soul/reference`, `/higgsfield-ai/popcorn/auto`, `/nano-banana`, `/flux-pro/kontext/max/text-to-image`, `/reve/text-to-image`, `/reve/remix`, `/reve/fast/remix`, `/reve/edit`, `/reve/fast/edit`.

Video model paths: `/higgsfield-ai/dop/{turbo,lite,standard}`, `/veo3.1` (+ `/fast`, `/image-to-video`, `/first-last-frame-to-video`, `/reference-to-video`), `/sora-2/{text-to-video,image-to-video}` (+ `/pro`), `/kling-video/v2.1/{master,pro,standard}/...`, `/kling-video/v2.5-turbo/{pro,standard}/...`, `/bytedance/seedance/v1/{lite,pro/fast}/{text,image}-to-video`, `/minimax/hailuo-02/{pro,standard}/...`, `/minimax/hailuo-2.3[-fast]/...`, `/wan-25-preview/{text,image}-to-video`.

**`POST /higgsfield-ai/soul/standard`** — required `prompt` (string); optional `num_images` (int 1–4, default 1), `resolution` (enum `["2K","4K"]`, default `"2K"`), `aspect_ratio` (enum `1:1,4:3,3:4,3:2,2:3,5:4,4:5,16:9,9:16,21:9`, default `"4:3"`).
> Docs conflict: `quickstart.md` and `index.md` both send `{"resolution":"720p"}`, which is **not** in the OpenAPI enum. Trust the spec; validate via `/estimate` first.

**`POST /higgsfield-ai/soul/reference`** — required `prompt`, `image_reference_url` (uri). Optional `seed` (1–1000000), `style_id` (uuid), `batch_size` (enum `[1,4]`), `resolution` (enum `["720p","1080p"]`, default `720p`), `aspect_ratio` (`9:16,16:9,4:3,3:4,1:1,2:3,3:2`), `enhance_prompt` (bool, default `true`), `style_strength` (float 0–1, default 1). → the practical style-consistency path for a branded channel.

**`POST /higgsfield-ai/soul/character`** — additionally requires `custom_reference_id` (uuid of a *trained* character) and `custom_reference_strength`. No character-training endpoint exists in the public spec → dashboard-only workflow, unusable server-side.

**`POST /higgsfield-ai/dop/{turbo,lite,standard}`** — required `prompt`, `image_url` (uri, "First frame image"). Optional `seed` (int 1–1000000, default null), `motions` (array of `MotionSchema` `{id: uuid, strength: 0-1}`, **maxItems 2**, default null), `end_image_url` (uri, default null, "Last frame image"), `enhance_prompt` (bool, default true). **No** `duration`, `seconds`, `resolution`, `quality`, or `aspect_ratio` property. Motion-preset UUIDs are not published anywhere.

DoP clip length: **5 seconds** (WaveSpeedAI's hosted Higgsfield DoP image-to-video documents a `duration_seconds` parameter with example value `5` and describes "5-second Image-to-Video clips"; Clipia's DoP page states "5 sec"). Output **resolution is unverified** — no primary or third-party source states it. Do not storyboard against 720p.

### 1.9 Higgsfield CLI (different product — do not confuse with the API)
`npm i -g @higgsfield/cli` (npm latest **1.1.23**, published 2026-08-08). Aliases `higgsfield`, `higgs`. Flow: `higgsfield auth login` (browser OAuth) then e.g. `higgsfield generate create text2image_soul_v2 --prompt "a cat in a spaceship"`. Also offers an MCP server. Its FAQ: "Do I need an API key? No… authenticate through your Higgsfield account" and "Higgsfield tools use the same credit system as the Higgsfield platform." Browser-OAuth only — **no documented headless/service-account flow**, and it is not a documented server API. Do not build a scheduler on it.

Pricing-page footnote: "Unlimited models and Free Generations on plans are accessible only via higgsfield.ai and are **NOT** accessible on MCP/CLI, Canvas or Supercomputer." No unlimited tier applies to the API.

---

## 2. Pricing: per image, per short video, monthly for ~40 images + 10 videos

### 2.1 Higgsfield API pricing — UNPUBLISHED
Higgsfield publishes **no** per-model API price. The only mechanism is a pre-flight estimate:
```
POST https://platform.higgsfield.ai/estimate/<model-path>   # identical body to the generation call
→ {"credits":"1.500","usd":"0.094"}
```
The docs immediately state: "The values above illustrate the response format. Use the estimate returned for your authenticated account as the authoritative amount." So `$0.094` / `1.5 credits` is a **format illustration, not a price**. Every page in `llms.txt` was checked; none carries a per-model price.

**Reseller anchors** (published, verifiable, NOT from `platform.higgsfield.ai`):
- Higgsfield DoP image-to-video via WaveSpeedAI: **$0.125 per 5-second video** (`https://wavespeed.ai/docs/docs-api/higgsfield/higgsfield-dop-image-to-video`)
- Higgsfield Text2Image Soul via Segmind: **$0.2175 per generation** (schema.org offer price on `https://www.segmind.com/models/higgsfield-text2image-soul`)
- order-of-magnitude planning: ~$0.09–0.12/image for Soul, $0.125/clip for DoP — **reseller-sourced**

Higgsfield consumer plans (a **separate billing system** from `platform.higgsfield.ai`): Starter $19/mo = 270 credits/mo, 2 parallel videos + 4 images; Plus $59/mo monthly or $47/mo annual = 1,200 credits/mo, 6 videos + 8 images parallel; Ultra $129/mo monthly or $99/mo annual = 3,000 credits/mo (6,000 / 9,000 tiers also offered), 8 videos + 8 images parallel. Business: TEAM $79 monthly / $65 annual per seat = 1,000 credits/seat/mo (min 2 seats); SCALE $215 / $150 annual per seat = 2,500 credits/seat/mo. Implied credit value $0.033–$0.070/credit. Starter monthly figure is inferred from a "No difference compared to monthly" footnote — **(unverified)**.

### 2.2 kie.ai (fixed conversion: 1 credit = $0.005 USD, 200 credits per $1; 5% or 10% bonus on larger SKUs)
Machine-readable, no auth required:
```
POST https://api.kie.ai/client/v1/model-pricing/page
body {"pageNum":N,"pageSize":100}     # pageSize max 100; 408 rows total
→ records of {modelDescription, interfaceType, provider, creditPrice, creditUnit, usdPrice, falPrice, discountRate}
```

Images (USD/image): Qwen z-image **$0.004** (0.8 cr, cheapest usable); Google nano-banana text-to-image **$0.02** (4 cr); nano-banana edit $0.02; nano-banana-2-lite 1K $0.02; gpt image 1.5 medium $0.02; flux-2 pro 1K $0.025; wan 2.7 image $0.024; seedream 5.0 Lite t2i $0.0275 (5.5 cr); seedream 4.5 $0.0325; Google nano banana 2 — 1K $0.04 / 2K $0.06 / 4K $0.09; Google nano banana pro 1–2K **$0.09**, 4K $0.12; gpt image 2 — 1K $0.03 / 2K $0.05 / 4K $0.08; google imagen4 fast $0.02, default $0.04, ultra $0.06.

Videos (USD): seedance-1.5-pro no-audio 720p **$0.0175/s** (5s ≈ $0.088); seedance-2-mini 720p no-video-input $0.041/s (5s ≈ $0.21); hailuo 02 i2v Standard 6s 512p $0.06, 6s 768p **$0.15**, 10s 768p $0.25; hailuo 02 Pro 6s 1080p $0.285; kling 2.1 Standard 5s $0.125, Pro 5s $0.25; kling 2.5 turbo Pro 5s **$0.21**, 10s $0.42; kling 3.0 turbo 720p $0.09/s; wan 2.5 i2v 5s 720p $0.30, 5s 1080p $0.50; Veo 3.1 Lite 720p $0.15/video, Fast 720p **$0.30**, Fast 1080p $0.325, Quality 720p $1.25.

### 2.3 fal.ai (official published prices)
Video: Wan 2.5 $0.05/s; Kling 2.5 Turbo Pro **$0.07/s** ("5s video = $0.35, +$0.07 per additional second"); Veo 3 $0.40/s; Ovi $0.20/video. Model-page detail: `minimax/hailuo-02/standard/image-to-video` = $0.045/s at 768P (~"6 second 768p video = $0.27"), ~$0.017/s at 512P; `wan-25-preview/text-to-video` = $0.05/s 480p, $0.10/s 720p, $0.15/s 1080p; seedance v1 pro fast 1080p 5s ≈ $0.243.
Images: Seedream V4 $0.03/image; Flux Kontext Pro $0.04; Nanobanana $0.0398 (model page: "$0.039 per image… 25 times for $1.00"); Qwen $0.02/megapixel.

### 2.4 Replicate (per-run, from pricing JSON embedded in each model page)
`google/nano-banana` $0.039/output image; `bytedance/seedream-4` $0.03/image; `qwen/qwen-image` $0.025/image; `black-forest-labs/flux-schnell` **$3.00 per 1,000 images ($0.003 each)**; `bytedance/seedance-1-lite` $0.018/s @480p, $0.036/s @720p, $0.072/s @1080p; `minimax/hailuo-02` 512P-6s $0.10, 512P-10s $0.15, 768P-6s $0.27, 768P-10s $0.45, 1080P-6s $0.48; `kwaivgi/kling-v2.5-turbo-pro` $0.07/s; `google/veo-3-fast` $0.10/s without audio, $0.15/s with audio; `wan-video/wan-2.5-t2v-fast` $0.068/s @720p, $0.102/s @1080p.

### 2.5 Segmind
`higgsfield-text2image-soul` **$0.2175/generation**; `nano-banana` $0.03636/image; `seedance-v1-lite-text-to-video` ~$0.1983/generation. Plans: Flexible pay-as-you-go (start with $10, 60 RPM, 1 GB storage); Pro $39/mo → $50 credits + 120 RPM + 10 GB; Business $99/mo → $99 credits + 500 RPM + 100 GB; Scale $599/mo → $599 credits + 1 TB. All plans include API access. Segmind's limit is **RPM**, not concurrency.

### 2.6 Monthly estimate — 40 images + 10 short (5s, 720p) videos
| Stack | Images | Videos | **Total/mo** |
|---|---|---|---|
| kie.ai floor | 40 × z-image $0.004 = $0.16 | 10 × seedance-1.5-pro 720p noaudio $0.088 = $0.88 | **$1.04** |
| **kie.ai budget (recommended)** | 40 × nano-banana $0.02 = $0.80 | 10 × kling-2.5-turbo-pro 5s $0.21 = $2.10 | **$2.90** (580 credits ≈ one $10 top-up per ~3 months) |
| kie.ai premium | 40 × nano-banana-pro $0.09 = $3.60 | 10 × Veo 3.1 Fast w/ audio $0.30 = $3.00 | **$6.60** |
| Replicate | 40 × nano-banana $0.039 = $1.56 | 10 × seedance-1-lite 720p 5s $0.18 = $1.80 | **$3.36** (floor $1.12 with flux-schnell + hailuo-02 512P) |
| Segmind | 40 × nano-banana $0.0364 = $1.46 | 10 × seedance-lite $0.198 = $1.98 | **$3.44** (+$10 minimum credit purchase) |
| fal.ai | 40 × nano-banana $0.039 = $1.56 | 10 × hailuo-02 768p 6s $0.27 = $2.70 | **$4.26** ($5.06 with Kling 2.5 Turbo Pro) |
| Higgsfield API | unpriced | unpriced | **unknown**; reseller anchor 40 × ~$0.10 + 10 × $0.125 ≈ $5.25 |
| Higgsfield consumer via CLI/MCP | — | — | **$19/mo fixed** Starter; workload uses ~45 of 270 credits |

**Verified:** kie.ai, fal.ai, Replicate, Segmind unit prices (fetched live from provider APIs/pages) and all arithmetic above.
**Estimated / not verified:** any Higgsfield API cost; Higgsfield consumer per-model credit costs (Soul 2.0 = 0.12 credits/image, DoP Standard = 7 credits/3s) — the verifier could not reproduce these from any source **(unverified — treat as unsourced, and note the "3s" is refuted, see §11)**.

Bottom line: media generation is **$1–7/month**, i.e. ~2–5% of a $50–150 budget. Choose on quality and reliability, not price.

---

## 3. Provider recommendation

**Pick: kie.ai primary, fal.ai fallback.** Replicate as second fallback. Higgsfield and Segmind rejected as primary.

Why:
- **kie.ai primary** — full price table is machine-readable *without credentials*, one `createTask` endpoint covers 400+ models (one adapter covers everything), 20 new-generation requests per 10 s (~100+ concurrent tasks) is ~100× this workload's need, HMAC-signed webhooks, 14-day output retention, and the cheapest credible per-unit pricing.
- **fal.ai fallback** — far more mature platform, officially published prices, configurable retention, unlimited requeue on concurrency. Costs roughly 1.5–4× kie.ai for identical upstream models. Acceptable as a failover, not as the default.
- **Higgsfield rejected as primary** — API pricing entirely unpublished, credentials behind a Clerk signup wall, per-account concurrency invisible until you have an account, model access is entitlement-gated (404 per account), no webhook signature, no idempotency key. Every one of those is an unpriced unknown for a scheduler that must fire twice a day.
- **Segmind rejected** — most expensive route ($0.2175/image for Soul, 5–10× kie.ai for comparable output) and a $10 minimum. Its only unique value: the **only** way to call Higgsfield Soul at a published, verifiable price without a Higgsfield account.
- **Replicate rejected as primary** — competitive prices (flux-schnell $0.003/image is the absolute floor) but **1-hour output retention** makes fire-and-forget scheduling dangerous, and accounts with granted credit but no payment method are throttled to 1 req/s / 6 req/min.

**Concrete model picks:** images via kie.ai `google/nano-banana` ($0.02) with `nano-banana-2` 1K ($0.04) as the quality tier; videos via kie.ai `kling 2.5 turbo Pro` image-to-video 5s ($0.21) or `hailuo 02 Standard` 6s 768p ($0.15). Reserve `Google veo 3.1 Fast 720p` ($0.30 with audio) for occasional hero posts. Budget $3–7/month.

**Fallback strategy — one interface, three adapters:**
```python
class MediaProvider(Protocol):
    async def submit(self, model: str, params: dict, webhook_url: str | None) -> str: ...   # -> job_id
    async def poll(self, job_id: str) -> tuple[JobStatus, list[str]]: ...                    # -> (status, urls)
    async def download(self, urls: list[str]) -> list[bytes]: ...
```
Adapters: `kie`, `fal`, `replicate`. Every provider is submit/poll-or-webhook async with a request/task id, so the abstraction is thin and switching providers is a config flag, not a rewrite. Per-provider terminal-status maps; one shared poller.

kie.ai openly self-describes as a small startup whose "overall stability may be slightly lower than official providers… a conscious trade-off" — which is precisely why the two-provider abstraction is mandatory, not optional.

**Price-drift monitor:** snapshot `POST https://api.kie.ai/client/v1/model-pricing/page {"pageNum":1,"pageSize":100}` (no auth) into Postgres monthly — returns credits, USD, and fal's comparison price for all 408 models.

### 3.1 Provider API shapes (for the adapters)

**kie.ai**
```
POST https://api.kie.ai/api/v1/jobs/createTask
  Authorization: Bearer <KEY>   Content-Type: application/json
  {"model":"google/nano-banana","callBackUrl":"https://…",
   "input":{"prompt":…,"aspect_ratio":…,"output_format":…,"nsfw_checker":true}}
→ {"code":200,"msg":"success","data":{"taskId":…}}

GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=…
→ data{taskId, model, state ∈ waiting|queuing|generating|success|fail,
       param (JSON STRING), resultJson (JSON STRING, e.g. {"resultUrls":[…]})}

GET https://api.kie.ai/api/v1/chat/credit         # balance
Keys: https://kie.ai/api-key
```
`resultJson` is a JSON-encoded **string** — `json.loads()` it before indexing `resultUrls`. State vocabulary differs from Higgsfield/fal.
Webhook security: enable `webhookHmacKey` at `https://kie.ai/settings`; callbacks carry `X-Webhook-Timestamp` (unix seconds) and `X-Webhook-Signature` = `base64(HMAC-SHA256(taskId + "." + timestamp, webhookHmacKey))`. Constant-time compare. `taskId` read from `req.body.data.task_id`.
Limits: 20 new generation requests / 10 s per account ("typically allows 100+ concurrent running tasks"); exceeding → HTTP 429 and the request does **not** enter the queue. Per-key hourly/daily/total caps and IP whitelisting configurable. Support hours UTC 21:00–17:00.

**fal.ai**
```
POST https://queue.fal.run/<model-id>    Authorization: Key $FAL_KEY
→ {request_id, response_url, status_url, cancel_url, queue_position}
Statuses: IN_QUEUE / IN_PROGRESS / COMPLETED
Webhook: ?fal_webhook=<url> on REST, or webhook_url= in the Python SDK
Delivery body: {request_id, gateway_request_id, status:"OK"|"ERROR",
  payload:{images:[{url, content_type, file_name, file_size, width, height}], seed},
  error, payload_error}
```
Retry policy: first attempt 15 s timeout, retries 120 s, up to **31 retries** with backoff until the stored result expires (~1 hour, or ~6 minutes for results ≥10 KB). **3xx redirects are a PERMANENT failure and never retried** — an `http://`→`https://` or trailing-slash redirect silently loses every result.
Concurrency: new accounts start at **2 concurrent requests**, scaling automatically with paid invoices over the last four weeks up to 40 self-serve; >40 requires sales. Queued requests are never dropped. Direct `run()` calls get HTTP 429 type `concurrent_requests_limit` with header `X-Fal-needs-retry: 1`. Prepaid credit, output-based billing; 5xx and queue wait time are never billed.

**Replicate**
Rate limits (documented): **600 req/min** for create-prediction, **3000 req/min** for all other endpoints including polling. Burst allowance above defaults. Degraded tier: accounts with granted credit but **no payment method on file** are capped at **1 req/sec, max 6 req/min** — a real trap for a VPS funded only with trial credit; attach a payment method. Throttle response: HTTP 429, body `{"detail":"Request was throttled. Your rate limit resets in ~30s."}` — back off ~30 s. Credit auto-reload above $20 recommended; stricter throttling as balance falls. Higher limits on request. **Concurrent-prediction ceiling is not documented (unverified).**

---

## 4. Media job pipeline design

### 4.1 Retention reality
| Provider | Generated output | Input uploads |
|---|---|---|
| Higgsfield | **≥7 days** | presigned upload URL expires 1 h; `x-amz-tagging: retention=temporary` |
| fal.ai | **≥7 days** default on the fal CDN; per-request override via header `X-Fal-Object-Lifecycle-Preference: {"expiration_duration_seconds": 3600}` (or `null` = no expiration). Request payloads stored 30 days by default; suppress with `X-Fal-Store-IO: 0`. Persistent `/data` volume retained indefinitely. "Expired files are permanently deleted and cannot be recovered." | — |
| kie.ai | **14 days**, then auto-deleted; log records (text/metadata) 2 months | 24 hours per one doc, 3 days per another on the same page → trust the per-response `expiresAt` field |
| Replicate | **1 HOUR** for outputs created through the API; `replicate.delivery` URLs expire after 1 hour. Only web-UI predictions persist. | — |

All three primary candidates converge at ≥7 days. **Do not write any provider-specific retention branch.** One rule satisfies everything: **download to VPS/object storage within 24 h of generation** — and in practice, immediately on completion.

Low-confidence addendum: search results claim kie.ai generated-image *download URLs* are signed and valid only ~20 minutes even though the file persists 14 days **(unverified — verify against docs.kie.ai)**. If true, that is the real operational constraint and reinforces "download on callback receipt, never lazily."

### 4.2 Durable-artifact rule
**Never store a provider URL as the durable artifact.** In the completion handler (webhook or poll):
1. Download bytes immediately.
2. Write to `/var/lib/tgbot/media` (or object storage).
3. Upload to Telegram.
4. Persist Telegram's **`file_id`** in Postgres.

Telegram retains files indefinitely and `file_id` can be re-sent without re-uploading. This makes Replicate's 1-hour and kie.ai's URL-signing windows irrelevant.

### 4.3 Timing against the 10:00 / 21:00 slots
- Video generation is **minutes-scale** and can terminate as `nsfw` or `failed`. The scheduler must never discover this at 09:59.
- Schedule generation **at least 30–60 minutes before** each post slot.
- Keep a **pre-rendered fallback image per post category** so a slot always has something to ship.
- App-level poll timeout: **10–15 minutes** per job.

### 4.4 Job state machine (Postgres `media_job`)
`QUEUED → SUBMITTED(provider_job_id) → IN_PROGRESS → {COMPLETED, FAILED, NSFW, CANCELED} → DOWNLOADED → UPLOADED(telegram_file_id)`

Rules:
- Persist `provider`, `provider_job_id`, `x_correlation_id`, `submitted_at` in the **same transaction** as the submit. No idempotency key exists on Higgsfield → an orphaned submit must be reconciled, never retried.
- Idempotency key for the worker task is `media_job.id`.
- Gate submissions with an `asyncio.Semaphore` sized below the provider's concurrency cap (Higgsfield: 4; fal new account: 2).
- Shared poller: 2.0 s initial, ×1.5, cap 10.0 s, ±0.5 s jitter, hard timeout; per-provider terminal-status map.
- Third-party media callbacks: expose on the same aiohttp app under a distinct path with its own HMAC / shared-secret check; the handler writes the result to Postgres and enqueues a follow-up task — **never do work inline in a third-party callback** (Higgsfield's 10 s response budget alone forbids it).

### 4.5 Text rendering — do not let a model draw Uzbek
Uzbek Latin uses `oʻ` and `gʻ` with **U+02BB** modifier letters plus digraphs (`ch`, `sh`, `ng`) — exactly the glyphs text-rendering models corrupt. **No provider makes any Uzbek-specific claim.** Nano Banana Pro (Gemini 3 Pro Image) is the strongest multilingual renderer (Google documents correct letterforms across Latin, Cyrillic, Arabic, Devanagari and layout-preserving in-image translation) but Google itself warns it "may struggle with grammar, spelling, cultural nuances" **(medium confidence generally; low specifically for oʻ/gʻ)**.

Design decision:
1. Generate **text-free** imagery. Append to every image prompt: `no text, no lettering, no captions, no signage, no watermark`.
2. Composite Uzbek text server-side with **Pillow** + a Latin-Extended font (Noto Sans / Inter / Montserrat).
3. Write image prompts in **English** — all these models are English-trained; the LLM prompt-agent translates the Uzbek post into an English visual brief. Uzbek text lives only in the Telegram caption and the Pillow overlay.

This guarantees correct `oʻ`/`gʻ`, costs nothing, keeps typography on-brand, is immune to model drift, and lets you use the cheapest models.

---

## 5. Python stack — concrete pins

```toml
# pyproject.toml (versions current as of 2026-08-12)
aiogram          = ">=3.30,<3.31"   # 3.30.0, 2026-07-17, py>=3.10,<3.15 — Bot API 10.2
apscheduler      = ">=3.11.3,<4"    # 3.11.3, 2026-06-28
sqlalchemy       = "2.0.52"         # 2026-08-11
alembic          = "1.19.1"         # 2026-08-08, py>=3.10
asyncpg          = "0.31.0"         # 2025-11-24  (psycopg 3.3.4 + psycopg-pool 3.3.1 is the more actively maintained alternative)
pydantic         = "2.13.4"         # aiogram requires pydantic<2.14,>=2.4.1
pydantic-settings= "2.15.0"
structlog        = "26.1.0"
anthropic        = "0.121.0"        # 2026-08-07
taskiq           = "0.12.4"         # 2026-05-08, py>=3.10
taskiq-redis     = "1.2.3"          # 2026-06-23
tenacity         = "9.1.4"
uvloop           = "0.22.1"
orjson           = "3.11.9"
dishka           = "1.10.1"         # async-native DI with aiogram integration
# aiohttp 3.14.3 — aiogram requires aiohttp<3.15,>=3.9.0
# tzdata — REQUIRED on slim/Alpine images (no system tz database)
# dev:
pytest-asyncio   = "1.4.0"          # 2026-05-26
testcontainers   = "4.15.0"
time-machine     = "3.4.0"
syrupy           = "5.5.3"
sentry-sdk       = "2.67.1"
# optional: aiogram-dialog 2.6.0
```
Install with **uv** from a committed `uv.lock`.

**Framework — aiogram 3.30.0.** It is the only candidate at Bot API 10.2 (Telegram released 10.2 on 2026-07-14; aiogram shipped support 2026-07-17). python-telegram-bot 22.8 (2026-06-12) supports only up to Bot API 10.0 (2026-05-08); its 10.1 support is an open issue (#5261, opened 2026-06-11) against the unreleased v23 milestone, and 10.2 is untracked. Rejected: **python-telegram-bot** (Bot API lag; its `JobQueue` is *literally* APScheduler — extras pin `apscheduler<3.12.0,>=3.10.4` — with a smaller API and a `run_daily(days=...)` trap where 0–6 map to **Sunday–Saturday**, so choosing PTB does not avoid the scheduler decision). Rejected: **Telethon** (stable 1.44.0 2026-06-15; 2.x still `2.0.0a0` from Oct 2025; MTProto session state, `api_id`/`api_hash` management, bot accounts have functional gaps such as no dialogs so `get_dialogs` fails, plus ban surface area) — reserve only if you later need historical channel scraping the Bot API cannot reach.

**aiogram Router observers (20 named).** `message`, `edited_message`, `channel_post`, `edited_channel_post`, `inline_query`, `chosen_inline_result`, `callback_query`, `shipping_query`, `pre_checkout_query`, `poll`, `poll_answer`, `my_chat_member`, `chat_member`, `chat_join_request`, `message_reaction`, `message_reaction_count`, `chat_boost`, `removed_chat_boost`, `errors`, and `update` (dispatcher-only). Routers nest via `include_router()` / `include_routers()`; updates cascade the tree, first match wins. `channel_post` and `message` are structurally separate observers → channel logic and discussion-group logic never share a filter chain, mapping 1:1 to `routers/channel.py` vs `routers/discussion.py` vs `routers/admin.py`.

**Comment-thread seeding.** A channel post auto-forwarded into the linked discussion group arrives in the GROUP as a `Message` with `is_automatic_forward=True` and `sender_chat` set to the linked channel. Replying to it (`reply_to_message_id`, or `message_thread_id`) posts a comment under the channel post. The bot must be a member of the discussion group. This is the exact mechanism for waking the quiet group: post to channel → wait for the `is_automatic_forward` echo → capture that `message_id` → reply. **(unverified for all configurations** — no primary doc confirms this holds when the group has topics enabled or anonymous admin posting is on; validate by hand against the real channel+group before building on it.)

**FSM.** `StatesGroup` + `State`; `FSMContext` methods `set_state()`, `get_state()`, `update_data()`, `get_data()`, `set_data()`, `clear()`. Storages shipped: `MemoryStorage`, `RedisStorage`, `MongoStorage`/`PyMongoStorage`. `FSMStrategy` has exactly five members, **verified at source** (`aiogram/fsm/strategy.py`, dev-3.x): `USER_IN_CHAT`, `CHAT`, `GLOBAL_USER`, `USER_IN_TOPIC`, `CHAT_TOPIC`. The module also exports `apply_strategy(strategy, chat_id, user_id, thread_id=None)` → 3-tuple: `CHAT`→`(chat_id, chat_id, None)`; `GLOBAL_USER`→`(user_id, user_id, None)`; `USER_IN_TOPIC`→`(chat_id, user_id, thread_id)`; `CHAT_TOPIC`→`(chat_id, chat_id, thread_id)`; default/`USER_IN_CHAT`→`(chat_id, user_id, None)`.
**None of the five keys on a post id** → per-post approval state genuinely cannot use a built-in strategy. Keep approval state in a Postgres `posts` table with a status enum; use FSM only for conversational admin flows ("send me the replacement caption").

**Do not install `aiogram[redis]`.** Its redis extra pins `redis[hiredis]<8,>=6.2.0` while redis-py is at 8.1.0 (2026-07-30) — an unresolvable conflict with anything wanting `redis>=8`, including taskiq-redis and Redis-backed limiters. Since state lives in Postgres, skip aiogram's Redis FSM storage entirely; otherwise pin `redis<8` project-wide.

**Job queue — Taskiq 0.12.4 + taskiq-redis 1.2.3**, run as a **separate systemd unit** so a stalled media API never blocks Telegram handling. Use `SimpleRetryMiddleware` with backoff; task timeout well above expected video duration; idempotent on `media_job.id`. Conservative substitute: **Dramatiq 2.2.0** (sync-first, strongest operational track record). **Reject arq** — its README states verbatim "In maintenance only mode: arq is in maintenance only mode, see #510"; issue #510 (opened 2025-10-18, still open) says maintainers "will continue to fix critical security issues... but don't expect work on new fixes"; latest release 0.28.0 (2026-04-16). **Reject Celery 5.6.3** as over-weight for one queue on a 2-vCPU box.
Caveats: comparative throughput rankings between Taskiq/Dramatiq/Celery come from third-party 2026 blogs, not primary docs — **(unverified)**. Dramatiq's official Celery comparison (`https://dramatiq.io/motivation.html`) is 2019 vendor marketing, self-labeled "It's possible that various bits of the table below are now outdated," and says nothing about shutdown. The strongest actual decision input is **version maturity**: Taskiq is **0.12.4 — pre-1.0, no stability guarantee**, vs Celery 5.6.3 and Dramatiq 2.2.0.
The Celery-zombie failure mode **is** upstream-documented (not blog folklore): celery/celery issues #8030 ("Worker stops consuming tasks after redis reconnection on celery 5.2.3"), #8091, #10205 ("Celery worker stops consuming Redis tasks after broker connection reset ... does not recover automatically"), #3877, #5037, discussions #7276 and #9095. Redis-broker-specific (multiple reporters say it does not reproduce on RabbitMQ); circulated workaround `celery -A proj worker --without-heartbeat --without-gossip --without-mingle`.

**Rate limiting — you must write it.** Telegram's official Bots FAQ, verbatim: "In a single chat, avoid sending more than one message per second... eventually you'll begin receiving 429 errors." / "In a group, bots are not be able to send more than **20 messages per minute**." / "For bulk notifications, bots are not able to broadcast more than about 30 messages per second, unless they enable paid broadcasts." Paid broadcast raises to 1000/s at 0.1 Stars per extra message but requires ≥100,000 Stars balance and ≥100,000 MAU — unreachable here.
20 msg/min in the discussion group = 1 reply per 3 s sustained, and that is the binding constraint. aiogram ships **no** rate limiter (PTB ships `AIORateLimiter` via its rate-limiter extra, `aiolimiter<1.3,>=1.1`); the documented aiogram approach is a custom outer middleware (`docs.aiogram.dev/en/latest/examples/middleware_and_antiflood.html`). Build a per-`chat_id` async token bucket wrapping outbound sends: **~1 message per 3.5 s for the discussion group**, ~1/s per private chat. Catch `aiogram.exceptions.TelegramRetryAfter` and sleep exactly its `retry_after` seconds, then one retry, then give up and log. ~40 lines, not optional at 3000+ members.

**LLM layer — Anthropic.** `AsyncAnthropic` drops straight into the aiogram event loop; optional higher-throughput backend `pip install anthropic[aiohttp]` then `AsyncAnthropic(http_client=DefaultAioHttpClient())`. Default request timeout **10 minutes**; `max_retries` default **2**, auto-retrying 408/409/429/5xx plus connection errors with exponential backoff. Per-request override via `client.with_options(timeout=..., max_retries=...)`. Large `max_tokens` without streaming raises `ValueError` (SDK refuses non-streaming requests it estimates >~10 min). **Do not wrap in tenacity for 429/5xx** — that is retry-squared, worst case tens of minutes. Bound every LLM call with `asyncio.wait_for` inside handlers so a slow API call never stalls a webhook response.

Models and pricing (per million tokens): `claude-opus-5` **$5 in / $25 out** (1M context, 128K max output); `claude-sonnet-5` **$3/$15** with an introductory **$2/$10 through 2026-08-31** (1M context); `claude-haiku-4-5` **$1/$5** (200K context, 64K output). Prompt caching: `cache_control {'type':'ephemeral'}` with optional `ttl '1h'`; cache writes ~1.25× (5m TTL) or ~2× (1h), reads ~0.1×. **Minimum cacheable prefix is model-dependent: 512 tokens on claude-opus-5, 1024 on claude-sonnet-5, 4096 on Opus 4.6 / Haiku 4.5** — below the minimum it silently does not cache. Batch API = 50% discount, up to 24 h turnaround.
Routing: `claude-haiku-4-5` for comment triage / spam classification / topic tagging; `claude-opus-5` for post drafting and the reply-quality agent. Put the stable Uzbek style guide, channel persona, and few-shot examples behind a `cache_control` breakpoint with `ttl='1h'` (the gap between the 10:00 and 21:00 posts is 11 hours, so the 1h TTL covers within-session bursts, not across slots); put the per-request brief **after** the breakpoint. Consider Batch API for the 21:00 post if drafted in the morning.

**Structured outputs make agents swappable.** `client.messages.parse(model=..., output_format=PydanticModel)` → `response.parsed_output` as a validated instance; raw form `output_config={'format': {'type':'json_schema','schema': {...}}}`. The older top-level `output_format` on `messages.create()` is deprecated. Schema limits: `additionalProperties: false` required on all objects; recursive schemas, min/max numeric constraints, and `minLength`/`maxLength` are unsupported (Python/TS SDKs strip these and validate client-side). Incompatible with citations (400) and with message prefilling. New schemas incur a one-time compile cost, then a 24 h cache.

**Thinking control:** `thinking={'type':'adaptive'}` plus `output_config={'effort': 'low'|'medium'|'high'|'xhigh'|'max'}`.

**Hostinger VPS — target KVM 2.** Specs verified on `https://www.hostinger.com/vps-hosting` 2026-08-12 under a "Summer Sale: up to 80% off" banner; every advertised price is a **24-month prepay** with a published renewal rate on the same card:

| Plan | Specs | Intro (24-mo term) | **Renewal** | List |
|---|---|---|---|---|
| KVM 1 | 1 vCPU / 4 GB / 50 GB NVMe / 4 TB | $6.49/mo | **$11.99/mo** | $19.49 |
| **KVM 2** | **2 vCPU / 8 GB / 100 GB / 8 TB** | $8.79/mo | **$14.99/mo** | $24.49 |
| KVM 4 | 4 vCPU / 16 GB / 200 GB / 16 TB | $12.99/mo | **$28.99/mo** | $42.99 |
| KVM 8 | 8 vCPU / 32 GB / 400 GB / 32 TB | $25.99/mo | **$49.99/mo** | $73.99 |

All plans: full root access, automatic **weekly** backups plus manual snapshots, 1 Gbps, one-click OS/app templates including Docker; 30-day money-back guarantee. **Budget against the renewal number: KVM 2 at $14.99/mo.** Note KVM 2 at $8.79/mo is **~$211 upfront**, not $8.79 due monthly, and prices are region/currency-localized.

---

## 6. Scheduling — Asia/Tashkent, restarts, missed runs

**Asia/Tashkent is a fixed UTC+5 zone with no DST and no future DST rules.** Verified directly against IANA tzdb (`https://data.iana.org/time-zones/tzdb/asia`, Uzbekistan section, lines 4125–4141):
```
Zone Asia/Tashkent  4:37:11 -           LMT  1924 May 2
                    5:00    -           %z   1930 Jun 21
                    6:00    RussiaAsia  %z   1991 Mar 31 2:00
                    5:00    RussiaAsia  %z   1992
                    5:00    -           %z
```
The terminal line has RULES `-` — no DST rules, unbounded into the future. `Asia/Samarkand` is identical in effect. Confirmed by local `zoneinfo`: 2026-01-15 and 2026-07-15 both give `utcoffset 5:00:00`, `dst() 0:00:00`, `tzname '+05'`. Last DST period was **1991-03-31 → 1991-09-29** (last change 1991-09-29 03:00, clocks back one hour); 1991-07 shows `dst()=1:00:00`, 1992-07 onward `0:00:00`.

Consequences: **10:00 and 21:00 Tashkent are always 05:00 and 16:00 UTC.** The nonexistent/ambiguous-local-time class of bug does not exist here. Still **do not hardcode +05** — keep the IANA name so a future government change is a `tzdata` update, not a code change and a missed post. One historical caveat: the +05:00 base offset itself only dates to the 1991-03-31 02:00 transition (Tashkent was on a 6:00 base before), so pre-1991 timestamp arithmetic must not assume +05.

**APScheduler 3.11.3** with `AsyncIOScheduler` + `MemoryJobStore` + `zoneinfo.ZoneInfo('Asia/Tashkent')`. Use `zoneinfo.ZoneInfo`, not `pytz.timezone` — 3.11.0 added ZoneInfo support and deprecated pytz; multiple 3.11.x patch releases fixed DST bugs introduced by that transition, so pin **>=3.11.3**, not >=3.11.0. (3.10.0 raised the SQLAlchemy floor to >=1.4 and fixed SQLAlchemy 2.0 compat.) Install `tzdata` on slim/Alpine images.

**APScheduler 4.0 is unusable.** Latest is `4.0.0a6` from 2025-04-27 (~15 months stale; the changelog's newest entry is "UNRELEASED"). Upstream states verbatim: "The v4.0 series is provided as a pre-release and may change in a backwards incompatible fashion without any migration pathway, so do NOT use this release in production!" 4.0 still has no automatic import path from a persistent 3.x job store. Its async DataStore/EventBroker (added in 4.0.0a1, "Added full async support (asyncio and Trio) via AnyIO") is **not available to this project**.

**Do not use SQLAlchemyJobStore with AsyncIOScheduler.** This is settled by source, not inference: in `apscheduler/schedulers/asyncio.py` (3.x branch), `AsyncIOScheduler.wakeup()` is decorated `@run_in_event_loop`, whose wrapper calls `self._eventloop.call_soon_threadsafe(wrapped)` — so `wakeup()` and the `self._process_jobs()` it calls execute **on the event loop thread**. In `schedulers/base.py`, `_process_jobs` (line 1140) acquires `self._jobstores_lock` (an RLock, line 1158) and calls the synchronous `jobstore.get_due_jobs(now)` (line 1161). `BaseJobStore` in 3.x defines no async methods. Every scheduler tick therefore performs blocking DBAPI I/O inside the event loop, by construction. Corollary: `scheduler.add_job()` and `remove_job()` take the same lock and hit the store synchronously, so a slow Postgres blocks update handling too, not just the tick.

**Configuration:**
```python
TASHKENT = ZoneInfo('Asia/Tashkent')
scheduler.add_job(tick, CronTrigger(hour=10, minute=0, timezone=TASHKENT),
                  id='post_morning', replace_existing=True,
                  coalesce=True, max_instances=1, misfire_grace_time=1800)
scheduler.add_job(tick, CronTrigger(hour=21, minute=0, timezone=TASHKENT),
                  id='post_evening', replace_existing=True,
                  coalesce=True, max_instances=1, misfire_grace_time=1800)
```
`add_job()` params: `id`, `trigger`, `misfire_grace_time`, `coalesce`, `max_instances` (default 1), `replace_existing`, `jobstore`.

**Restart / missed-run semantics.** After a restart, a job whose run time has passed is a "misfire"; APScheduler checks each missed run against `misfire_grace_time` and skips runs outside it. `coalesce=True` collapses multiple missed runs into one. `replace_existing=True` avoids duplicate jobs when re-registering against a persistent store. `misfire_grace_time=1800` = post up to 30 minutes late, then **skip and alert** — an AI-education channel posting yesterday's 10:00 content at 03:00 is worse than skipping.

**The scheduler must not decide what to post.** It fires an **idempotent tick** that:
1. queries Postgres for the approved post whose `scheduled_for` slot is due and whose `status` is still `'approved'`,
2. transitions it to `'sending'` **under a row lock**,
3. sends,
4. sets `'sent'`.

Missed runs, double fires, and restarts all become no-ops. Since the two triggers are static, nothing needs to be persisted in APScheduler at all — durable state lives in your own tables.

**Rejected:** celery-beat (a second broker and two more processes for two cron entries); a hand-rolled `asyncio.sleep` loop (you would reimplement misfire and DST semantics badly).

---

## 7. Webhook vs polling — verdict: **webhook**

**Decisive fact:** long polling permits exactly **ONE** `getUpdates` consumer per bot token. A second consumer causes HTTP **409** `Conflict: terminated by other getUpdates request; make sure that only one bot instance is running`. This fires during overlapping deploys, dev/prod sharing a token, and restart races where the old polling loop is not torn down. Overlap-based zero-downtime restart is therefore **structurally impossible** in polling mode. Webhooks have no such constraint — the reverse proxy holds connections while the backend swaps. Webhooks also cut idle traffic to zero on a small VPS.

**Telegram webhook constraints (hard):** ports **443, 80, 88, 8443 only** — "Other ports are not supported and will not work." TLS **1.2+** mandatory (SSLv2/3, TLS 1.0/1.1 unsupported). Self-signed certs allowed but require uploading the PEM public cert as `multipart/form-data` in `setWebhook`, with CN/SAN matching the webhook host. Telegram sends from **149.154.160.0/20** and **91.108.4.0/22** (subject to change).

`setWebhook` params: `url` (required), `certificate` (InputFile), `ip_address`, `max_connections` (1–100, default 40), `allowed_updates` (array of strings), `drop_pending_updates` (bool), `secret_token` (1–256 chars, only `A-Z a-z 0-9 _ -`). Telegram sends the secret in the **`X-Telegram-Bot-Api-Secret-Token`** header on every webhook POST.
`getUpdates` params: `offset`, `limit` (1–100, default 100), `timeout` (long-poll seconds, default 0), `allowed_updates`.

**Concrete setup:**
- Caddy (simplest automatic TLS) or nginx + certbot terminating TLS on **443** for a real subdomain, reverse-proxying to the aiohttp app on `127.0.0.1:8080`.
- `aiogram.webhook.aiohttp_server.SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=SECRET).register(app, path='/tg/<long-random-segment>')` plus `setup_application(app, dp, bot=bot)`. `SimpleRequestHandler` also accepts `handle_in_background=`.
- Never `TokenBasedRequestHandler` — aiogram documents it as not recommended because the token appears in the URL and can be logged by reverse proxies.
- `setWebhook(..., secret_token=SECRET, allowed_updates=['message','edited_message','channel_post','callback_query','my_chat_member'])` to cut update volume.
- Defense in depth: verify the `X-Telegram-Bot-Api-Secret-Token` header; allowlist `149.154.160.0/20` and `91.108.4.0/22` at the firewall or in nginx (aiogram also ships `aiogram.webhook.security.IPFilter` / `ip_filter_middleware`).
- Keep long polling as a documented flag for local development, against a **separate dev bot token** — a developer running locally with the production token silently kills production polling.

**For media-provider callbacks on the same VPS:** prefer **polling** unless you already terminate public HTTPS with a valid cert — which, having set up the Telegram webhook, you do. So: use kie.ai webhooks with HMAC verification (`base64(HMAC-SHA256(taskId + "." + timestamp, key))` in `X-Webhook-Signature`), and if you use Higgsfield's webhook, treat the callback as a trigger and re-read `status_url` with credentials since it has no signature. Expose media callbacks on the same aiohttp app under distinct paths.

**Graceful shutdown.** `Dispatcher.start_polling()` takes `handle_signals=True` (default — it installs SIGINT/SIGTERM handlers itself) and `close_bot_session=True`; `Dispatcher.stop_polling()` stops programmatically. Under systemd with `KillSignal=SIGTERM` this drains cleanly out of the box. Under Docker the Python process must be PID 1 with proper signal handling (exec-form ENTRYPOINT, or `init: true` / tini) or SIGTERM is swallowed and the container is SIGKILLed, dropping in-flight updates — aiogram issue #591 is exactly this failure mode (a PID-1 forwarding problem, not an aiogram defect).

---

## 8. Deployment, supervision, secrets, migrations, backups

### 8.1 systemd, not docker compose
On a single small VPS with one Postgres and two or three Python processes, Docker adds an image build, a registry or on-box build step, ~200–400 MB overhead, and the PID-1 signal trap, for zero orchestration benefit.

Four units:
| Unit | Role |
|---|---|
| `postgresql` | distro package |
| `tgbot-migrate.service` | `Type=oneshot`, `ExecStart=alembic upgrade head`, `RemainAfterExit=yes` |
| `tgbot.service` | aiohttp webhook app; `After=` / `Requires=` the migrate unit |
| `tgbot-worker.service` | Taskiq worker (separate process from the bot) |

Key settings: `Restart=always`, `RestartSec=5`, `KillSignal=SIGTERM`, `TimeoutStopSec=30` (let aiogram drain), `Environment=PYTHONUNBUFFERED=1`, `EnvironmentFile=/etc/tgbot/env`.
Hardening: `User=tgbot`, `NoNewPrivileges=yes`, `PrivateTmp=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, `ReadWritePaths=/var/lib/tgbot/media`.

### 8.2 Secrets
Single **root-owned, chmod 600 `/etc/tgbot/env`** loaded via systemd `EnvironmentFile=`, parsed by **pydantic-settings 2.15.0** into a typed `Settings` object at startup so a missing or malformed value fails fast at boot rather than at 21:00. **Never** use systemd `Environment=` lines — readable by any user via `systemctl show`. Never commit `.env`. Separate `BOT_TOKEN` for dev and prod (this also prevents the 409 self-inflicted outage). Rotate the Telegram webhook `secret_token` and the Anthropic key on a schedule — both are one-line edits plus a restart. Store the restic repository password in the same file **and keep a copy off the machine** (a backup you cannot decrypt after losing the VPS is worthless).

### 8.3 Migrations
**Alembic 1.19.1**, `alembic init -t async <dir>` (also `pyproject_async`), env.py sharing the app's async engine config — cookbook recipe "Using Asyncio with Alembic." Programmatic execution: put a live `Connection` into `Config.attributes['connection']` before `command.upgrade(cfg, 'head')`.
Health gate: `alembic current --check-heads` is now a first-class CLI command (backed by `MigrationContext.get_current_heads()` vs `ScriptDirectory.get_heads()`) — run it in `/healthz` so the bot refuses to serve against a stale schema.
Practices: enforce one head (fail CI on multiple heads); name every constraint via a SQLAlchemy `MetaData` `naming_convention` so autogenerate produces stable diffs; hand-review every autogenerated migration (autogenerate misses server defaults, enum changes, index renames). Test in CI with testcontainers 4.15.0 and a real Postgres: `upgrade head` from empty, then `downgrade -1` and upgrade again.
Because migrations run to completion before the app starts, **never write a migration incompatible with the currently-running code** — use expand/contract: add nullable column → deploy code → backfill → deploy code → drop old column.

### 8.4 Zero-downtime restarts
Only achievable in webhook mode. Simplest sufficient pattern at this scale: run the bot on a unix socket or fixed localhost port behind Caddy/nginx and accept a sub-second gap on `systemctl restart` — Telegram retries failed webhook deliveries. For true zero-gap: two units on different ports with an nginx upstream, drained one at a time. Never attempt this with long polling (409).

### 8.5 Logs & observability
Log to stdout with **structlog 26.1.0** emitting JSON; let systemd capture into the journal; configure `/etc/systemd/journald.conf` with `SystemMaxUse=1G` and `Storage=persistent`. Do **not** hand-roll file rotation. Add **sentry-sdk 2.67.1** for exception aggregation (free tier fits the budget). Expose `/healthz` on the aiohttp app checking Postgres connectivity and `alembic current --check-heads`. Put a correlation id (`post_id` or `update_id`) into every log line via structlog contextvars so one post's journey (scheduler → agent → approval → send) is greppable.

### 8.6 Backups — three tiers with an explicit RPO
**Tier 1 (nightly, the real one):** systemd timer at 03:30 Tashkent running
```
pg_dump -Fc … | restic backup --stdin --stdin-filename db.dump
restic backup /var/lib/tgbot/media        # same run → DB and media captured at the same point
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
```
against off-site object storage (Backblaze B2 or S3, a few dollars/month).

**Tier 2:** if a 24 h RPO is unacceptable, add WAL archiving (`archive_command` shipping to the same bucket) or adopt pgBackRest for true PITR — **only after tier 1 is proven**. `pg_dump` is a logical export with no PITR; a dump taken hours before corruption loses everything since. WAL-G is the Go/cloud-first alternative pushing directly to S3/GCS with ~16 concurrent upload streams and no dedicated backup server.

**Tier 3:** Hostinger's **weekly** VM snapshot — a whole-machine disaster fallback only. Weekly is far too coarse for a content database; up to 7 days of channel content, comment history, and media metadata is not an acceptable RPO.

**Non-negotiable: a monthly RESTORE DRILL** — `restic restore` into a scratch container, `pg_restore`, confirm row counts and the newest post match. An untested backup is not a backup.

**Crypto correction:** restic derives keys with **scrypt**, not Argon2id. Restic: AES-256-CTR (confidentiality) + Poly1305-AES (authentication), keys derived from the password via **scrypt** (N/r/p + salt stored in the key file; design.rst shows the on-disk field `"kdf": "scrypt"`), 32 bytes total overhead (16-byte IV + 16-byte MAC), layout `IV || CIPHERTEXT || MAC`; 64 derived key bytes split 32 for AES-256 and 32 for Poly1305-AES (the latter split into a 16-byte AES key `k` plus 16 bytes secret `r`). "argon" appears zero times in restic's design.rst and CHANGELOG.md. **Argon2 is BorgBackup's KDF** — argon2id via argon2-cffi, random 256-bit salt per key, KEK wrapping with chacha20-poly1305; Borg data modes `aes256-ocb` / `chacha20-poly1305`, with older repokey/keyfile modes using AES-CTR-256 + HMAC-SHA256 encrypt-then-MAC and repokey-blake2/keyfile-blake2 substituting BLAKE2b-256. scrypt is memory-hard and entirely adequate here; the pg_dump-into-restic recommendation is unaffected.

**"pgBackRest is the de facto 2026 standard" is unfalsifiable editorial** — no PostgreSQL primary source endorses a third-party backup tool as standard (the postgresql.org wiki Backup_and_Restore page returns 404). Dropped as a claim; the conservative pg_dump-into-restic design does not depend on it.

**Not checked (unverified):** whether Hostinger blocks outbound port 25 or applies egress filtering affecting off-site backup uploads or webhook egress; Hostinger's stance on running Postgres on their VPS templates. Both are almost certainly fine on a full-root KVM instance.

---

## 9. Project layout — deterministic spine + swappable prompt-agents

```
tgcm/
  __main__.py                 # composition root only: Settings, engine, bot, dp, scheduler, wire agents, run
  settings.py                 # pydantic-settings Settings; fail-fast validation

  core/                       # DETERMINISTIC SPINE — no LLM imports; enforce with an import-linter rule
    models.py                 # SQLAlchemy 2.0 DeclarativeBase: Post, PostRevision, Comment, MediaJob,
                              #   ApprovalEvent, ScheduleSlot
    enums.py                  # PostStatus: DRAFT -> PENDING_CONTENT -> PENDING_FINAL -> APPROVED
                              #   -> SENDING -> SENT | REJECTED | FAILED
    repo/                     # one module per aggregate; every method takes an AsyncSession; NO business logic
      posts.py  comments.py  media.py
    state_machine.py          # pure functions: (current_status, event, actor) -> new_status | TransitionError
                              #   fully unit-testable, zero I/O
    scheduling.py             # APScheduler wiring + the idempotent due-post tick
    ratelimit.py              # per-chat token bucket + TelegramRetryAfter handling
    clock.py                  # now_tashkent() indirection so tests can freeze time

  agents/                     # SWAPPABLE PROMPT-AGENTS — the only place the Anthropic SDK is imported
    protocol.py               # typing.Protocol per role + Pydantic output models (the contract)
    base.py                   # shared client, cache_control breakpoint placement, model routing, usage logging
    drafter.py                # channel post drafting (claude-opus-5)
    commenter.py              # discussion-group reply generation (claude-opus-5)
    triage.py                 # comment classification / spam / topic tagging (claude-haiku-4-5)
    prompts/                  # *.md prompt bodies, version-controlled and diffable, loaded not inlined
    fakes.py                  # deterministic Protocol implementations used by tier-1 tests

  bot/                        # TELEGRAM EDGE — thin; handlers orchestrate, they do not contain logic
    app.py                    # aiohttp app, SimpleRequestHandler, setup_application, /healthz, media callback route
    middlewares/              # db session-per-update, structlog correlation id, rate limit, error boundary
    routers/
      channel.py              # @router.channel_post(...)
      discussion.py           # @router.message(F.chat.id == DISCUSSION_ID) — incl. is_automatic_forward capture
      admin.py                # @router.message + @router.callback_query in the private admin group
    keyboards.py              # InlineKeyboardMarkup builders
    callbacks.py              # CallbackData factories: ApprovalCB(action, post_id, gate)
    renderers.py              # DB row -> Telegram message text/entities. Pure, snapshot-testable.

  workers/
    tasks.py                  # Taskiq broker + task definitions (video generation, media fetch)
    media.py                  # MediaProvider adapters: kie.py, fal.py, replicate.py

  migrations/                 # alembic -t async
  tests/
    fakes/session.py          # the BaseSession fake — the testing foundation
    unit/  integration/  evals/
```

**Three load-bearing boundary rules:**
1. `core/` never imports `agents/` or `bot/` — the spine is testable with zero network and zero LLM.
2. `agents/` never imports `bot/` and never touches the database — an agent takes a typed brief and returns a typed result, nothing else.
3. `bot/routers/` handlers contain no business logic — they parse the update, call `core/` or `agents/`, and render.

**What makes an agent swappable:** one `Protocol` per role, e.g. `class PostDrafter(Protocol): async def draft(self, brief: Brief) -> DraftedPost`, with `client.messages.parse(output_format=DraftedPost)` guaranteeing the JSON. The spine depends on the Pydantic contract, not on the prompt, the model, or the provider. Replacing `drafter.py` with a different model, a different provider, or a hardcoded fake requires changing exactly one file and zero call sites.

---

## 10. Testing strategy

### 10.1 The hard constraint: temperature is gone
**`temperature`, `top_p`, and `top_k` are REMOVED from the Anthropic Messages API on all current models** — `claude-opus-5`, `claude-sonnet-5`, `claude-opus-4-8`, `claude-opus-4-7`, and `claude-fable-5` all return **HTTP 400** if any of them is sent. `budget_tokens` is likewise removed (400). Anthropic never had a `seed` parameter. Any test plan reading "set temperature=0 for reproducibility" is **dead on arrival**.

Anthropic's own documentation states results are not fully deterministic even at temperature 0 (and it no longer exists). Production LLM inference is non-deterministic due to GPU batch-dependent floating-point summation order, multi-datacenter routing, and MoE expert routing varying with batch composition **(mechanism explanations: medium confidence, corroborated by 2026 practitioner writeups)**. The answer is **structural, not a parameter**.

### 10.2 aiogram ships no test harness — budget the work
`MockedBot` lives at `tests/mocked_bot.py` **inside the repo**, is not exported in the installed package, and there is **no `aiogram.test_utils` module**. The third-party `aiogram-tests` is dead: last PyPI release **1.0.3 on 2022-10-26**, and issue #15 ("Broken with recent version of aiogram" — importing the removed `aiogram.utils.helper`) open since **2023-04-23** with no fix.

You will write your own ~100-line fake session: subclass `aiogram.client.session.base.BaseSession`, record outgoing API method calls, return canned responses, and feed hand-built `Update` objects through `dp.feed_update(bot, update)`.

### 10.3 Three sharply separated tiers

**Tier 1 — fast, hermetic, the bulk (CI).**
- Fake the Telegram transport via the `BaseSession` subclass; build `Update` / `Message` / `CallbackQuery` as plain Pydantic models; push through `dp.feed_update(bot, update)`; assert on the recorded outgoing calls.
- Fully mock the Anthropic client **at the agent-protocol boundary** — swap in `agents/fakes.py` implementations of each `Protocol`. Handlers never see a real client.
- `pytest-asyncio 1.4.0`; `time-machine 3.4.0` (faster and more correct than freezegun for tz-aware code) to freeze at **09:59:59 Tashkent** and assert the scheduler tick fires exactly once.
- `state_machine.py` is pure functions with zero I/O → drive every legal and illegal transition.
- `renderers.py` output is deterministic → **syrupy 5.5.3** snapshot tests are appropriate here, and **never** for raw LLM output.

**Tier 2 — integration (CI).**
- testcontainers 4.15.0 real Postgres for repository tests and migration tests (`upgrade head` from empty, `downgrade -1`, upgrade again).
- Idempotency tests: run the scheduler tick twice against a due post and assert exactly one send.
- Provider adapters against recorded fixtures — including the kie.ai `resultJson`-as-string trap and each provider's terminal-status vocabulary.

**Tier 3 — evals, explicitly NOT in CI.**
- A separate `make eval` suite hitting the real Anthropic API **N times per prompt**.
- Validate every response against the agent's Pydantic output model (`messages.parse` → `parsed_output`).
- Score with rubric assertions: Uzbek language detected, length in range, no banned phrases, required sections present.
- Report **mean / stddev / worst-case**. Gate prompt changes on this, never on byte-exact snapshots.
- Assert `usage.cache_read_input_tokens > 0` in a smoke test — a silently-invalidated cache is the single most common way this budget blows up.

### 10.4 Cache-invalidation trap (test for it)
Any timestamp, UUID, or f-string-interpolated "today's date" placed in the system prompt sits at the **front** of the cache prefix and invalidates the entire cache on every request. Put volatile content **after** the last `cache_control` breakpoint. Treat `cache_read_input_tokens == 0` across repeated calls as a bug, not a curiosity.

---

## 11. What did NOT survive verification

**REFUTED — dropped entirely:**

1. **"Higgsfield DoP produces ~3-second clips at 720p."** DoP produces **5-second** clips (WaveSpeedAI documents `duration_seconds` with example value `5` and "5-second Image-to-Video clips"; Clipia states "5 sec"). The "7 credits/3s" pricing row could not be reproduced from any source. The **720p half is separately unverified** — no primary or third-party source states DoP output resolution. Do not budget or storyboard against 720p.

2. **"fal.ai's default generated-media retention is unknown / undocumented."** fal.ai's official FAQ states it verbatim: "Generated media files (images, videos, audio) are stored on the fal CDN and available for **at least 7 days** by default." The `media-expiration` page's "Configurable" row describes the *control mechanism*, not the absence of a default.

3. **"kie.ai output retention is 24 hours (two docs contradict: 14 days vs 24 hours)."** Not a contradiction — two different objects. **Generated output = 14 days.** The 24-hour figure applies to **uploaded input files** (`docs.kie.ai/file-upload-api/quickstart`), which itself self-contradicts later with "3 days after upload" — so trust the per-response `expiresAt` field for uploads. Log records = 2 months. **Do not "assume 24 hours."**

4. **"Replicate's API rate limits are undocumented / unknown."** They are documented at `https://replicate.com/docs/topics/predictions/rate-limits`, verbatim: "You can create predictions at **600 requests per minute**. All other endpoints you can call at **3000 requests per minute**." Plus burst allowance, the 1 req/s + 6 req/min degraded tier for accounts with granted credit but no payment method, credit auto-reload above $20 recommendation, and the 429 body `{"detail":"Request was throttled. Your rate limit resets in ~30s."}`. (Genuinely still unknown: Replicate's concurrent-prediction ceiling.)

5. **"Restic uses AES-256-CTR + Poly1305 + Argon2id."** Restic uses **scrypt**, not Argon2id — `design.rst` line 340 shows `"kdf": "scrypt"` and line 350 "This is then used with ``scrypt``, a key derivation function"; zero hits for "argon" across design.rst and CHANGELOG.md. Argon2 is **Borg's** KDF. See §8.6 for the corrected crypto.

6. **"pgBackRest is the de facto 2026 production standard."** Unfalsifiable editorial from blog roundups. No PostgreSQL primary source endorses any third-party backup tool as standard.

7. **"Uzbekistan's DST abandonment date is disputed (1991 vs 1995)."** No 1995 source could be located; primary (IANA tzdb) and secondary (timeanddate.com) sources agree the last change was **1991-09-29 03:00**. Drop the caveat.

8. **"aiogram's FSMStrategy member names are unverified and need source confirmation."** Confirmed at source (`aiogram/fsm/strategy.py`, dev-3.x): exactly five members, names match one-for-one with no extras or omissions. Downgrade from risk to verified.

9. **"APScheduler 3.x SQLAlchemyJobStore blocking the event loop is an inference; benchmark it."** Not an inference — settled by reading the 3.x source (see §6). **Drop "benchmark it."** The MemoryJobStore recommendation stands on source evidence, and the corollary (`add_job`/`remove_job` also block) was missed by the original claim.

10. **"Third-party blogs: Higgsfield top-up credits expire in 90 days."** Official docs say **one year** after being added. Blogs are describing the consumer app or are stale.

**DOWNGRADED / newly marked unverified:**

- **Higgsfield consumer credit costs** (Soul 2.0 = 0.12 credits/image; DoP Lite 3 cr/3s, Turbo 5 cr/3s, Standard 7 cr/3s; Kling 2.5 Turbo 720p 4 cr/5s; Seedance 1.5 720p 3 cr/5s; Veo 3.1 Fast 720p 11 cr/4s; Sora 2 720p 10 cr/4s; Hailuo 02 768p 6 cr/6s; Reve 0.25, Nano Banana 1, Seedream 1, GPT Image 1, FLUX.2 Pro 1, Popcorn 1.5, Flux Kontext 1.5, Nano Banana Pro 4K 4) — **could not be reproduced by the verifier from any source**. `higgsfield.ai/pricing` and scopeful.org expose no per-model credit table without JS. **Treat all as unverified**, not merely "a separate billing system."
- **Higgsfield OpenAPI path count "50 paths / 48 model endpoints"** — **not verified.** The verifier's independent parse returned 28 but was self-assessed as unreliable (likely markdown-conversion truncation). Make `len(spec['paths'])` a runtime deploy assertion, not a build-time constant.
- **Whether the Higgsfield API needs a paid subscription or only a credit balance** — still uncertain (Clerk wall). Signal *against* "credits alone suffice": `404 = "Request or model not found for this account"` means model availability is entitlement-gated, and `rate-limits.md` names "subscription" as a limiter. Posture: assume a paid subscription **may** be required for specific models; probe with a cheap `/estimate` call per model at integration time.
- **Higgsfield Starter monthly price ($19/mo)** — inferred from a "No difference compared to monthly" footnote. Medium confidence.
- **Whether the Higgsfield CLI can authenticate headlessly on a VPS** — not verified that a copied credential file survives on a headless host.
- **Which models a given Higgsfield API account can actually call** — the 48 endpoints are the *catalogue*, not a guarantee of access.
- **Uzbek-specific text-rendering quality for any model** — zero providers make an Uzbek claim; the Nano Banana Pro multilingual assessment is generic (Cyrillic/Arabic/Devanagari) and partly secondary coverage. Medium confidence generally, **low specifically for `oʻ`/`gʻ`**.
- **Taskiq / Dramatiq / Celery comparative throughput and shutdown rankings** — third-party blogs only. The only first-party Taskiq benchmark is a maintainer's personal gist (s3rius, gist `91c39494fe1b96ad467cee671dfdf5ec`). Dramatiq's official Celery comparison is 2019 vendor marketing that says nothing about shutdown.
- **kie.ai signed-download-URL ~20-minute window** — from search results, not a primary docs page. Verify against docs.kie.ai.
- **Bot reply to an `is_automatic_forward` message rendering as a comment in ALL linked-group configurations** (topics enabled, anonymous admin posting) — no primary doc. Validate by hand.
- **Hostinger egress filtering / port 25 / Postgres-on-VPS stance** — not checked.

**PROMOTED (was a caveat, is now solid):**
- Hostinger pricing is confirmed promotional with **published renewal rates on the same card** — budget KVM 2 at **$14.99/mo**, and note the intro price requires ~$211 upfront for 24 months and is region/currency-localized.
- Higgsfield ≥7-day output retention, and the no-charge/auto-refund policy for failed/nsfw/canceled requests — confirmed across three docs pages.
- The Celery Redis-broker zombie-worker failure mode — **upstream-documented** in celery/celery issues #8030, #8091, #10205, #3877, #5037 and discussions #7276, #9095. Higher confidence than originally assigned.

---

## Surprises

1. **Higgsfield, the nominal starting point, is the only provider you cannot price.** Zero published API prices anywhere; the one number in the docs is explicitly labeled a format illustration; credentials are behind a Clerk wall; concurrency limits are invisible until you have an account; model access is entitlement-gated per account. The "obvious" provider is the one that must be rejected as primary.
2. **Media generation is a rounding error.** $1–7/month for 40 images + 10 videos, against a $50–150 budget. Cost should not drive the provider decision at all; retention, reliability, and webhook authenticability should.
3. **Higgsfield returns HTTP 400 for concurrency exhaustion, not 429** — no `Retry-After`, no rate-limit headers, only a human-readable string. A conventional "4xx = permanent failure" handler silently drops jobs.
4. **Higgsfield generation POSTs have no idempotency key, and the docs say so explicitly.** A retry on an ambiguous timeout creates a second *billed* generation. This inverts the usual "retry on timeout" reflex.
5. **`temperature=0` no longer exists.** The single most common LLM-testing recipe returns HTTP 400 on every current Anthropic model, and there is no `seed`. Determinism must be achieved architecturally.
6. **Replicate deletes API outputs after ONE HOUR** while every other candidate keeps them ≥7 days. Any "generate now, post at 21:00" design that stores only a URL breaks silently on Replicate.
7. **fal.ai treats a 3xx from your webhook as a permanent failure with no retry.** An `http→https` upgrade or a trailing-slash redirect loses every result — with 31 retries otherwise available, this is a uniquely quiet way to lose data.
8. **PTB's JobQueue *is* APScheduler**, with a smaller API and a Sunday=0 weekday convention. Choosing PTB does not avoid the scheduler decision; it just hides it behind a trap.
9. **Neither aiogram test utilities nor an aiogram rate limiter exist.** Both are things PTB ships and aiogram does not — roughly 140 lines of work that must be budgeted explicitly rather than discovered at 3000-member scale.
10. **Asia/Tashkent's fixed +05 removes the hardest scheduling bug class entirely** — no nonexistent or ambiguous local times, ever. 10:00/21:00 Tashkent are permanently 05:00/16:00 UTC.
11. **APScheduler 4.0 has been an alpha for 15 months** with upstream saying it may break "without any migration pathway" and "should NOT be used in production." Every blog recommending its async data stores is recommending abandonware.
12. **arq — the long-standing default async-Redis queue recommendation — is officially maintenance-only** per its own README and issue #510.
13. **The cheapest sensible design deliberately avoids the models' headline feature.** In-image text rendering is exactly what you must not use: generate text-free imagery, composite Uzbek with Pillow. This simultaneously fixes `oʻ`/`gʻ` correctness, cuts cost, and removes model-drift risk.
14. **kie.ai publishes its complete 408-model price table over an unauthenticated POST endpoint** — a free, automatable price-drift monitor with zero credentials.

## Open questions

1. What does `POST https://platform.higgsfield.ai/estimate/higgsfield-ai/soul/standard` actually return for a real funded account? (Requires signup. This is the only way to price Higgsfield.)
2. Does a funded Higgsfield account without a paid subscription get access to `soul/*` and `dop/*`, or does it 404? What concurrency cap does a fresh account get (the docs' example says 4)?
3. What resolution does Higgsfield DoP output? No source states it.
4. Where do the Higgsfield motion-preset UUIDs (`motions[].id`, maxItems 2) come from, and is there any non-dashboard path to character training for `soul/character`'s `custom_reference_id`?
5. How many paths does `openapi.json` actually contain today? (Assert at deploy time.)
6. Are kie.ai generated-media download URLs really signed for only ~20 minutes despite 14-day file retention?
7. Does a bot reply to an `is_automatic_forward` message reliably render as a comment when the discussion group has topics enabled or anonymous admin posting on?
8. Does Hostinger apply any egress filtering that would affect restic uploads to B2/S3 or outbound API calls?
9. Is Taskiq's pre-1.0 status (0.12.4) acceptable for a 24/7 production bot, or should Dramatiq 2.2.0's maturity win despite the sync-first ergonomics?
10. Does the `claude-sonnet-5` introductory rate ($2/$10) actually expire 2026-08-31, and what is the post-expiry budget impact?
11. What is the real Higgsfield credit-to-model cost table on the consumer plan? None of the cited figures could be independently reproduced.
