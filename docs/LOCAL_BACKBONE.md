# Spanish Dub Study: local-first durable backbone

This document defines the long-term dependency policy for the stable Spanish Dub Study runtime.
The stable path must continue to produce usable subtitles and speech without Gemini, OpenRouter, or
any other quota-limited generative API. Cloud analysis may return later only as an explicit optional
quality layer.

## Reliability rule

Every core stage should have a local/offline floor wherever Android makes that possible. A network
or experimental service may improve quality, but a failure, quota limit, model retirement, or API
change must not stop the pipeline behind it.

## Dependency tiers

| Stage | Stable floor | Optional quality layer | Durability / notes |
| --- | --- | --- | --- |
| Source timing and subtitle pairing | Local Java stores/algorithms | none required | Highest durability; owned in this repo. |
| Caption acquisition | YouTube Innertube caption track + signed timedtext, manual/ASR recovery | none | Inherently tied to YouTube internals; keep isolated behind TranscriptFetcher and diagnostics. |
| English -> Spanish translation | **Target: ML Kit on-device Translation** with downloaded EN/ES models | current no-key Google web translator as compatibility fallback | ML Kit is an official on-device Android SDK and should become the backbone. The current `client=gtx` web endpoint is convenient but not a contractual API and must not remain the sole long-term translator. |
| Spanish speech | **Target: Android System TTS with an installed voice that does not require network** | Edge consumer TTS for higher voice quality | Platform TTS is the reliability floor. Edge is unofficial/brittle and must fail forward rather than stall the dub. |
| Phrase scheduling / sync / replay / vocabulary | Local Java | none required | Highest durability; no network dependency. |
| Visual context | **Target: local frame capture + local vision** | future opt-in VLM/cloud analysis | First prove PixelCopy capture of the playback surface. Start with ML Kit OCR/image labels; evaluate a pinned mobile image-text embedding model only if richer semantics are needed. |
| Speaker diarization | **Target: local PCM tap + pinned offline diarizer** | future opt-in cloud analysis | `sherpa-onnx` is a viable offline diarizer, but it is not useful until decoded source PCM can be captured reliably inside patched YouTube. Never fake speaker identity from subtitle text. |

## Translation plan

1. Keep v2.10 stable on Google translation while removing all Gemini runtime calls.
2. Add ML Kit Translation as a separate local adapter, not mixed into timing or UI code.
3. Download English and Spanish models deliberately and expose model readiness in diagnostics.
4. Prefer local ML Kit when ready.
5. If the local model is unavailable or still downloading, use the existing Google web translator as
   a compatibility fallback; never block caption display while waiting for a model download.
6. Cache accepted translations in the existing bounded/local structures where appropriate.

## TTS plan

1. Keep Edge as an optional quality engine, but bound timeouts and cool failed phrases so one request
   cannot monopolize synthesis.
2. Enumerate Android TTS voices and prefer a Spanish voice whose `isNetworkConnectionRequired()` is
   false for the reliability fallback.
3. If Edge synthesis fails or the ready buffer drains because Edge is unhealthy, fail forward to the
   offline system voice for the current/near phrases rather than going silent.
4. Diagnostics must state the actual engine and voice used for each failover.

## Local visual-context experiment

The first experiment is a **capture probe**, not a semantic model:

1. Locate the actual YouTube playback `SurfaceView`/`Surface` (or a safe player-window region).
2. Use Android `PixelCopy` to sample a downscaled frame without MediaProjection.
3. Log success/failure, frame dimensions, player mode, and capture latency; do not save frames to
   storage by default.
4. If capture is stable across fullscreen/minimized/inline playback, add sparse local analysis:
   - OCR for visible names, titles, signs, slides, scoreboards, etc.
   - image labels for broad object/scene hints.
5. Feed the resulting small set of facts into a local rolling context store. Do not let visual hints
   rewrite source captions unless confidence and alignment checks explicitly allow it.
6. If broad labels are insufficient, evaluate a pinned mobile image-text embedding model (for example
   MobileCLIP-class models) with a small candidate vocabulary derived from the transcript. Keep the
   model/version/hash explicit and benchmark battery, RAM, and latency before making it stable.

## Local speaker-diarization experiment

Speaker recognition is blocked by **audio capture**, not by lack of offline diarization models.

1. Build a capability probe that attempts to tap decoded PCM inside the YouTube playback path.
2. It must not require microphone recording, room-audio capture, or a permanent MediaProjection
   prompt for the stable UX.
3. Verify sample rate/channels, continuity across pause/seek, behavior in fullscreen/minimized/inline,
   and whether audio offload bypasses the hook.
4. Only after PCM is proven, integrate a pinned offline diarizer such as sherpa-onnx:
   - VAD / segmentation
   - speaker embeddings
   - conservative clustering with hysteresis
   - anonymous A/B/C identities only
5. Store only small rolling embeddings/profiles in memory by default; do not save source audio.
6. If the PCM tap is not reliable, leave speaker recognition disabled in stable builds rather than
   substituting transcript heuristics.

## Traceability requirements

For every third-party model/native library promoted to stable:

- Pin an exact version/tag/commit.
- Record model filename, source, license, SHA-256, expected input/output shape, and approximate size.
- Keep a small deterministic smoke test or known-vector test where feasible.
- Put the dependency behind one adapter/interface so it can be replaced without changing subtitle,
  translation, or transport logic.
- Diagnostics must distinguish `local`, `network fallback`, and `experimental` execution.
- A failed optional layer must never disable captions, translation dispatch, or TTS scheduling.

## Stable vs experimental builds

**Stable:** local-first backbone, no quota-limited generative API calls, deterministic failure recovery.

**Experimental:** may enable Gemini/VLM/cloud diarization or heavier local models, but those features
must remain opt-in and must not alter the stable fallback path when disabled or unavailable.
