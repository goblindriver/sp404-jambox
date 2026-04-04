# Chat → Code: Session 3 Wrap Brief

**Date:** April 4, 2026
**From:** Chat
**To:** Code Agent
**Re:** Current state, retag health check, architecture priorities, and what's next

---

## First: The RL Pipeline Pitch Is Approved

The cross-media taste profiler, multitrack ingestion, clip extraction, DPO training architecture — all approved. The production/consumption taste profile split is exactly right. The philosophy statement in `taste_profile_production.json` nails it.

Chat's full creative direction response is in `docs/HANDOFF_CHAT_RL_RESPONSE.md` (or in Downloads as `CHAT_RESPONSE_rl_pipeline.md`). The key points:
- Production profile (hype > warm > soulful) is the optimization target
- Consumption profile (nostalgic > dark > dreamy) is context, not target
- `wrong_vibe_polarity` added as a high-priority error type
- Retag review UX spec: table view with inline editing, not one-at-a-time approval
- Movie clip priority: blaxploitation and kung fu first (production value), not horror
- Multitrack artist mappings refined (Stevie Wonder → soulful + hype + warm, NIN noted as consumption-side)

---

## Retag Health Check: Two Concerns

I looked at `data/retag_checkpoint.json` and there are flags:

### Concern 1: Speed — 42.5s per file

At 42,565ms average per file and 30,718 total files, the current run will take **~362 hours (15 days)**. That's not an overnight pass — that's a sustained run.

**Jason's call: let it run.** The 32b model produces significantly better tags than 8b and is likely multipurpose (vibe prompts, taste profiling, DPO teacher model). The quality tradeoff is worth the time. Results accumulate continuously — fetch starts improving as soon as the first batches complete.

**What Code should do:**
- Make sure the M3 can sustain this without thermal issues (monitor temps if possible)
- Verify checkpoint/resume is solid — a crash at day 12 shouldn't lose 12 days of work
- Consider running in priority order (Tiger Dust demand files first) so the most useful tags land earliest
- The re-vibe pass with the production prompt can target a subset (high-priority files only) rather than re-running all 30K

### Concern 2: Error Rate — 96/250 = 38%

96 errors out of 250 processed files is a 38% error rate. That's high enough to investigate before letting the run continue for 15 days.

**Questions:**
- What are the errors? LLM timeout? Malformed JSON? Librosa failures on corrupt files?
- Are they concentrated in specific file types or directories?
- Are they recoverable (retry would succeed) or permanent (corrupt files)?

If most errors are LLM timeouts on the 32b model under sustained load, that reinforces Option 2 above. If they're corrupt files, flag them and move on.

---

## Architecture Priorities (from Bug Hunt 2)

Full report in `BUG_HUNT_2_ARCHITECTURE.md` (in Downloads or docs/). Top items:

### ARCH-1: _tags.json → SQLite Migration (CRITICAL)

This needs to happen before the retag finishes writing 30K enriched entries. A flat JSON file at that scale with feature vectors = 50-100 MB rewrites on every batch, race conditions with the watcher, and slow reads for fetch scoring.

**Recommendation:** Build `data/library_tags.sqlite` with indexed tables for tags and features. Migrate existing `_tags.json` entries. Smart retag writes directly to SQLite. Keep a JSON export function for backward compatibility.

This is the single highest-impact infrastructure change. It unlocks:
- Type code indexes for fetch scoring (OPT-1: 15x speedup)
- Safe concurrent access from watcher + retag + webapp
- Feature vectors as blobs (only load for similarity queries)
- Incremental writes (one row per file, not full file rewrite)

### ARCH-5: LLM Retry Logic

The 38% error rate makes this urgent. Smart retag needs:
- 3 retries with exponential backoff (2s, 4s, 8s)
- Failed files logged with error message
- `--retry-errors` flag to re-process only failed files
- Ollama health check at batch boundaries

### ARCH-2: Freesound Removal Fallback

After removing Freesound API: when fetch finds zero local matches for a pad, what does the user see? Verify it's a clear "no match" state, not a silent empty pad.

---

## Updated CLAUDE.md

The refreshed CLAUDE.md is in Downloads. Key additions since last version:
- Tiger Dust Block Party as the default set (10 banks, full pad layouts)
- Smart retag as next priority with feature store architecture
- Multi-resolution dedup (Chromaprint → MFCC → CLAP)
- Unified ingest pipeline with all features documented
- Power button UI
- Audio analysis (librosa), stem splitting (Demucs) — both live
- SP-404A Field Manual as #1 reference
- Sub pad is a modifier button, NOT a 13th sample slot
- Banks A-B are internal memory (survive card swaps)
- Production vs consumption taste profiles
- 5 new type codes: GTR, HRN, KEY, STR, RSR

---

## Documents in Downloads for You

| Document | What It Is |
|----------|-----------|
| `CLAUDE.md` | Full refresh — drop into repo root |
| `HANDOFF_SESSION3_FINAL.md` | Clean session handoff → `docs/` |
| `CHAT_RESPONSE_rl_pipeline.md` | Creative direction for RL pipeline → `docs/` |
| `CHAT_ACK_retag_status.md` | Quick ack on taste profile implementation → `docs/` |
| `BUG_HUNT_2_ARCHITECTURE.md` | Architecture bugs + optimization opportunities → `docs/` |
| `SMART_RETAG_SPEC.md` | Updated spec with architecture section → `docs/` |
| `OPTIMIZATION_PLAN.md` | 4-tier optimization roadmap → `docs/` |
| `CODE_BRIEF_optimization_measurements.md` | Measurement assignments (after retag) → `docs/briefs/` |
| `SP404A_FIELD_MANUAL.md` | Reviewed field manual as markdown → `docs/` |
| `SP404_ECOSYSTEM_RESEARCH.md` | SP-404 ecosystem map → `docs/` |
| `COWORK_BRIEF_tooling_and_horizon.md` | Cowork tooling + project horizon → `docs/briefs/` |
| `presets/genre/*.yaml` (×10) | Tiger Dust Block Party presets → `presets/genre/` |
| `sets/tiger-dust-block-party.yaml` | Tiger Dust set definition → `sets/` |

---

## Assignment Priority Order

### NOW (while retag runs):
1. **Investigate retag errors** — what's causing 38% failure rate? Fix the pipeline, don't restart the run.
2. **SQLite migration** — build `library_tags.sqlite`, migrate existing tags. Smart retag should write to SQLite, not JSON. Do this before 30K entries land in a flat file.
3. **LLM retry logic** — 3 retries with backoff, `--retry-errors` flag. The 38% error rate means we're losing a third of our work.
4. **Verify checkpoint resilience** — the 32b run will take ~15 days. A crash at day 12 can't lose everything. Test kill + resume.

### AFTER retag completes:
5. **Targeted re-vibe pass** with production prompt — only on Tiger Dust demand files + quality 3-4 borderline files. Don't re-run all 30K — the 32b tags are good, just need production-profile vibes on the files that matter most.
6. **Install Tiger Dust presets + Session 2 presets** — all in Downloads.
7. **Optimization measurements** — coverage report, tag audit, base vs RAG eval, fetch dry run, performance baselines. See `CODE_BRIEF_optimization_measurements.md`.

### WHEN READY:
8. **Retag review UI** — table view with inline editing per Chat's UX spec in RL pipeline response.
9. **DPO training infrastructure** — correction store, preference pair export, training script.
10. **CLAP embedding pass** — after retag is validated and library is clean.

---

## The Big Picture

The project philosophy crystallized this session: **party at the end of the world.** Consumption is dark (McCarthy, Berserk, NIN). Production is joyful (four-on-the-floor, community, dancing). The SP-404 is the antidote.

Everything we optimize for should serve the production profile. Quality 5 = makes people dance. The Tiger Dust sound lives in the overlap — warm danceable grooves with dusty degraded undertones.

The SP-404A Field Manual is the #1 LLM training data source. Feed it into RAG. The 29-effect reference with resample chain recipes is exactly what the model needs to understand the instrument.

We're building the leanest, meanest, smartest 404 package ever. RAWR.

— Chat
