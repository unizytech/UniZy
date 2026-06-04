# Fix: WebM init header relocation before stitching

A portable write-up of the WebM "header in the wrong chunk" bug and its fix, so
it can be replicated in any repo that inherited the same chunked-recording
strategy (MediaRecorder → base64 chunks → server-side stitch → speech-to-text).

---

## 1. Symptom

A recording fails at transcription with a generic decoder error. With Google
Gemini the exact error is:

```
ERROR - Error transcribing audio: 400 INVALID_ARGUMENT.
{'error': {'code': 400, 'message': 'Request contains an invalid argument.', 'status': 'INVALID_ARGUMENT'}}
```

Any media decoder (ffmpeg, Whisper, a browser) will reject the same bytes — this
is **not** a Gemini-specific problem. An upstream audio-quality probe may also
flag the container as `"Audio container unparseable"` / `speech_detected: false`.

It is **intermittent**: the same client/clinic/template that works most of the
time occasionally produces a corrupt recording. In our data, ~18 of a few
hundred inspectable sessions had this defect, and **~17 of those 18 failed** —
i.e. when it happens, it is almost always fatal.

---

## 2. Root cause

### Background: how MediaRecorder chunking works

`MediaRecorder` with a `timeslice` emits a stream of Blobs. The container's
**initialization segment** — for WebM/Matroska that's `EBML header + Segment +
Info + Tracks` (codec config) — is written **once**, normally at the very start
of the **first** Blob. Every later Blob is just raw **Cluster** data (audio
packets) with no header.

So a healthy recording looks like:

```
chunk 0: [EBML init][cluster…]   ← header lives here
chunk 1: [cluster…]
chunk 2: [cluster…]
...
```

Server-side stitching concatenates the chunks in index order, and because the
header leads chunk 0, the result is a valid streaming WebM file.

### The bug

Intermittently MediaRecorder emits the **first Blob without the init segment**,
and the header lands in **chunk 1 (or even chunk 2)** instead:

```
chunk 0: [cluster…]              ← NO header (raw cluster data)
chunk 1: [EBML init][cluster…]   ← header ended up here
chunk 2: [cluster…]
...
```

Now a naive index-order concat produces a buffer whose header sits **mid-stream**:

```
[cluster…][EBML init][cluster…][cluster…]...
          ↑ header in the middle → invalid container → decoder 400
```

The byte sequence to look for:

| Element | Hex magic | Meaning |
|---|---|---|
| EBML header | `1A 45 DF A3` | start of a well-formed WebM/Matroska file |
| Cluster | `1F 43 B6 75` | start of an audio-packet cluster |

The init segment is **everything in the header-carrying chunk before its first
`1F 43 B6 75`**.

### Why the indices are *not* wrong

Chunk ordering is correct and must be preserved — `chunk_index` reflects the true
audio timeline. The defect is purely **where the header bytes physically sit**,
not the order of the audio. The fix must therefore relocate only the header, and
**must not reorder chunks** (e.g. do not move chunk 1 ahead of chunk 0).

### Confirming it on a real session (SQL)

If chunks are stored base64 in Postgres, you can prove the diagnosis without
pulling bytes into your app. `position(... in ...)` is 1-based; `0` means absent.

```sql
SELECT chunk_index,
       length(decode(audio_data,'base64'))                                  AS len,
       position('\x1a45dfa3'::bytea in decode(audio_data,'base64'))         AS ebml_pos,
       position('\x1f43b675'::bytea in decode(audio_data,'base64'))         AS cluster_pos
FROM audio_chunks
WHERE session_id = '<failing-session>' AND chunk_index IN (0,1,2)
ORDER BY chunk_index;
```

A failing session shows `ebml_pos = 0` for chunk 0 and `ebml_pos = 1` for chunk 1.
Confirm exactly one chunk in the whole session carries the header:

```sql
SELECT
  COUNT(*) FILTER (WHERE position('\x1a45dfa3'::bytea in decode(audio_data,'base64')) = 1) AS chunks_starting_with_ebml,
  COUNT(*) AS total_chunks
FROM audio_chunks WHERE session_id = '<failing-session>';
```

Expect `chunks_starting_with_ebml = 1`.

To gauge prevalence across the fleet (only sessions whose chunks haven't been
purged are inspectable):

```sql
WITH stats AS (
  SELECT session_id,
         MIN(CASE WHEN left(audio_data,4)='GkXf' THEN chunk_index END) AS header_at_index
  FROM audio_chunks GROUP BY session_id            -- 'GkXf' = base64 of 1A45DFA3
)
SELECT header_at_index, COUNT(*) sessions,
       SUM((pj.status='ERROR')::int) errored
FROM stats st LEFT JOIN processing_jobs pj ON pj.session_id = st.session_id
GROUP BY header_at_index ORDER BY header_at_index NULLS LAST;
```

> Note: `1A 45 DF A3` base64-encodes to a string starting `GkXf`, so you can
> filter on `left(audio_data,4) = 'GkXf'` directly on the stored base64.

---

## 3. The fix

**Strategy: extract → strip → prepend, preserving chunk order.**

1. If chunk 0 already starts with the EBML magic → do nothing (fast path).
2. Otherwise scan the first N chunks (N=3) for the one that starts with the EBML
   magic and contains a Cluster.
3. **Extract** that chunk's init segment (bytes before its first Cluster).
4. **Strip** the init from its carrying chunk (keep only that chunk's Cluster
   data) — so the header is not duplicated mid-stream.
5. **Prepend** the single init segment to the front.
6. Concatenate everything else in original index order.

Result — exactly one header, clean cluster data, original timeline:

```
[EBML init] + chunk0(cluster) + chunk1(cluster only) + chunk2(cluster) + ...
```

If none of the first N chunks has a header, fall back to plain concat (nothing
to recover) and log a warning.

### Reference implementation (language-agnostic pseudocode)

```
EBML_MAGIC  = bytes(1A 45 DF A3)
CLUSTER_ID  = bytes(1F 43 B6 75)

extract_init(chunk_bytes):
    if not chunk_bytes.startswith(EBML_MAGIC): return None
    idx = chunk_bytes.find(CLUSTER_ID)
    if idx <= 0: return None            # no cluster, or no header before it
    return chunk_bytes[0:idx]

normalize_header_order(decoded_chunks, max_scan = 3):
    if decoded_chunks is empty: return decoded_chunks
    if decoded_chunks[0].startswith(EBML_MAGIC): return decoded_chunks   # fast path
    for i in 0 .. min(max_scan, len)-1:
        init = extract_init(decoded_chunks[i])
        if init:
            decoded_chunks[i] = decoded_chunks[i][len(init):]   # strip header off carrier
            return [init] + decoded_chunks                       # prepend once
    log_warning("no EBML header in first N chunks; passing through")
    return decoded_chunks
```

Call `normalize_header_order(...)` only for WebM/Matroska mime types
(`audio/webm`, `video/webm`, `audio/x-matroska`, `video/x-matroska`), then
`join` the resulting byte list. Do not apply it to PCM/WAV/MP4 — those have
different container rules.

### Actual Python implementation in this repo

- `backend/services/audio_splitter.py`
  - `_EBML_MAGIC = b"\x1a\x45\xdf\xa3"`, `_WEBM_CLUSTER_ID = b"\x1f\x43\xb6\x75"`
  - `_extract_webm_init_segment(chunk_bytes)` — extract step
  - `_scan_for_webm_init(decoded_chunks, max_scan=3)` — find header in first N
  - `normalize_webm_header_order(decoded_chunks, max_scan=3)` — full guard (the
    function to reuse)
- `backend/services/audio_stitcher.py`
  - `_stitch_webm_chunks(...)` decodes all chunks, then for WebM mime types runs
    `normalize_webm_header_order(...)` before `b"".join(...)`.

---

## 4. Two stitching paths — cover both

This codebase stitches in two places; a port should audit for the same.

1. **Full-recording stitch** (`stitch_audio_chunks` → `_stitch_webm_chunks`):
   used when the whole recording is transcribed at once. Apply the guard before
   joining.

2. **Segment-range stitch** (`stitch_and_get_bytes_for_chunk_range`): used for
   parallel/segmented transcription of a slice `[start..end]`.
   - If the slice **includes chunk 0** (start of recording), run the same
     `normalize_webm_header_order` over the slice.
   - If the slice **starts mid-recording** (`min_index > 0`), the slice has no
     header at all. Find the init among the **full recording's first 3 chunks**
     (it may be in 0, 1, or 2) and prepend it once. (The pre-existing code only
     looked at chunk 0; it must scan 0–2.)

---

## 5. Why existing safety nets didn't catch it

- **Inline→Files-API retry** (a Gemini-specific fallback) only triggers for
  small files sent inline; large recordings go straight to the Files API, which
  *also* rejects the malformed container. No recovery.
- **400 is not retried** (only 429/RESOURCE_EXHAUSTED is) — correct, since
  retrying identical malformed bytes just fails again.
- The container-corruption probe only tripped on `duration < 1s`; an unparseable
  long recording slipped through to the transcription call.

Optional hardening (not required by the fix): gate transcription on the
audio-quality probe's "container unparseable" signal and fail fast with a
"please re-record" message instead of spending a doomed API call.

---

## 6. Verification (how this fix was validated)

1. **Real-bytes proof (SQL)** on the failing production session: confirmed chunk
   0 header-less, 146-byte init in chunk 1, exactly 1 header across all 113
   chunks (queries in §2).
2. **End-to-end code test with ffmpeg decode**: built a real WebM/Opus file with
   many small clusters (`ffmpeg -cluster_time_limit 200 -cluster_size_limit
   8192`), reproduced the exact defect shape (header moved out of chunk 0 into
   chunk 1), ran it through the real `stitch_audio_chunks` and
   `stitch_and_get_bytes_for_chunk_range`, and asserted the output:
   - starts with the EBML magic at offset 0,
   - contains exactly **one** EBML header (no mid-stream duplicate),
   - preserves total cluster bytes,
   - decodes in ffmpeg (`ffmpeg -i out.webm -f null -` returns 0).
   - Control case (header already in chunk 0) takes the fast path and stays
     valid.

### Replication test checklist for the other repo

- [ ] `extract_init` returns `None` for a header-less chunk and the init prefix
      for a header-carrying chunk.
- [ ] `normalize_header_order` is a **no-op** when chunk 0 already has the header
      (assert the returned list is unchanged / fast path).
- [ ] header-in-chunk-1 and header-in-chunk-2 cases both produce a single-header
      stream that your decoder accepts.
- [ ] **chunk order is preserved** (compare the cluster byte sequence before vs
      after — only the header moved).
- [ ] no-header-anywhere case falls back to plain concat + warning (doesn't
      raise).
- [ ] both the full-stitch and the segment-range paths are covered.

---

## 7. Performance / latency notes

- The fast path is a single `startswith` on chunk 0 → negligible for the ~96% of
  recordings that are well-formed. Important if the stitch is on a
  latency-sensitive transcription path.
- The recovery path is cheap byte slicing/concatenation, only on the broken
  minority.
- No new awaited/network calls; pure in-memory transform.

---

## 8. The real long-term fix is client-side

Server-side relocation is a robust safety net, but the defect originates in the
browser. The durable fix is to ensure the **first `dataavailable` Blob always
carries the init segment** before it is indexed as chunk 0 (e.g. validate the
first Blob's leading bytes, or buffer until the header is present). Keep the
server guard regardless — clients in the wild will keep producing this.
