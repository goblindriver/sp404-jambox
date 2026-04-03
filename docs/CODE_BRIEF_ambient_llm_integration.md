# Code Brief: Ambient LLM Integration — "It Just Knows"

## Design Philosophy

The LLM should be invisible. No chat boxes, no "AI generated" badges, no separate "AI features" section. The entire app just feels smarter than it should. Users shouldn't think "I'm using AI right now" — they should think "this app really gets me."

**Core principles:**
- The LLM never announces itself
- Every integration point should feel like a natural extension of the existing UI
- Text inputs that accept natural language should look identical to existing inputs — just smarter
- LLM-enhanced results mix seamlessly with rule-based results
- Failures are silent — if the LLM endpoint is down, everything degrades gracefully to current behavior
- Speed matters — if a response takes more than 1-2 seconds, it should feel instant through optimistic UI updates or background processing

All LLM calls go through a single internal function that handles the endpoint, timeouts, fallback, and prompt construction. Each integration point just passes its context and gets structured output back.

---

## Integration Points

### 1. Preset Browser — "Describe a Vibe" Field

**Where:** Text input at the top of the preset browser sidebar, above the search/filter controls.

**UX:** Looks like a search field. Placeholder text: "describe a vibe..." User types something like "jungle breaks, dark, 170" and hits enter. A preset card appears at the top of the list with a subtle sparkle or shimmer indicator. It's generated on the fly but looks like any other preset. User can drag it to a bank slot, save it, or ignore it.

**What the LLM does:**
- Receives the natural language prompt
- Returns structured preset YAML: name, slug, bpm, key, vibe, tags, and all 12 pad descriptions
- System prompt includes the preset format spec, valid type codes, keyword guidelines (3-4 per pad)
- Generated preset gets a `source: vibe-prompt` tag to distinguish from `source: curated`

**Graceful degradation:** If LLM is unavailable, the field acts as a regular keyword search against existing preset names/tags.

**Builds on:** Existing `vibe_generate.py` + `rank_library_matches()`. This is an extension — instead of returning ranked samples, return a full preset.

---

### 2. Pad Editing — "Something Grittier"

**Where:** Pad detail view / pad edit modal, wherever you currently edit a pad's fetch keywords.

**UX:** Small text input below the keyword editor. Placeholder: "refine this pad..." User types a plain language adjustment like "darker" or "more acoustic" or "less busy." Keywords update in place, library re-scores, new top match loads on the pad. The text input clears after applying — it's a verb, not a state.

**What the LLM does:**
- Receives: current pad type code, current keywords, current matched sample info, user's refinement text
- Returns: updated keyword list (still 3-4 keywords, still following the format spec)
- This is a *delta*, not a full rewrite — the LLM should understand it's adjusting, not starting from scratch

**Graceful degradation:** Field hidden if LLM unavailable. Keyword editor works as before.

---

### 3. Smart Ingest Tagging

**Where:** Invisible. Runs during the ingest pipeline after the rule-based auto-tagger.

**UX:** No UI change. Tags in `_tags.json` are just richer and more accurate than they used to be. User never sees this happen.

**What the LLM does:**
- Receives: filename, file path, any `_SOURCES.txt` content, neighboring filenames in the same pack, existing auto-generated tags
- Returns: enriched tag list — fills gaps the rule-based tagger misses
- Example: rule-based tagger sees `funky_drummer_break_140.wav` and tags it `[drums, break, 140bpm]`. LLM adds `[funk, classic-break, james-brown, uptempo]` because it understands the cultural reference.

**Constraints:**
- LLM tagging runs AFTER rule-based tagging, as enrichment — never replaces
- Must not slow down ingest noticeably. If the endpoint is slow, queue LLM enrichment as a background job and update `_tags.json` async.
- Tag enrichments get a flag in `_tags.json` so we know which tags are rule-based vs. LLM-enriched (useful for debugging/tuning later)

**Graceful degradation:** If LLM unavailable, ingest works exactly as it does today. No change.

---

### 4. Thoughtful Daily Bank

**Where:** Enhances existing `daily_bank.py`.

**UX:** The daily bank already generates a preset. The change is qualitative — it goes from "algorithmically selected trending tags" to "curated with intent." The preset might come with a one-line note: "heavy on the breaks today — you've been exploring a lot of melodic content lately, so here's something percussive to balance it out."

**What the LLM does:**
- Receives: trending.json data, recent ingest log, recent fetch/play history, current library tag distribution, day of week / time
- Returns: a preset (standard YAML format) plus a short curator's note (1-2 sentences)
- The LLM should act like a thoughtful DJ friend who knows your library and suggests something you wouldn't have picked yourself

**Curator's note display:** Shown subtly in the daily bank card in the preset browser. Not a notification — just there when you look at it.

**Graceful degradation:** Falls back to current algorithmic daily bank if LLM unavailable.

---

### 5. Fetch Result Insights

**Where:** Subtle tooltip or secondary text on fetch results when browsing/auditioning samples.

**UX:** When you're looking at sample matches for a pad, each result has a faint secondary line explaining why it scored high. Something like "matched: vinyl + dark + 92 BPM" or "Plex mood: brooding, played 47 times." Not always visible — maybe on hover or in an expanded detail view.

**What the LLM does:**
- Receives: the sample's `_tags.json`, Plex metadata, the pad's fetch keywords, the final score breakdown
- Returns: a short natural language explanation (under 10 words)
- This could also be done WITHOUT the LLM using template strings from the scoring breakdown. Start with templates, upgrade to LLM later if the templates feel too robotic.

**Graceful degradation:** Template-based explanations if LLM unavailable.

**Note:** This is the lowest-priority LLM integration. Start with templates. The LLM version is a polish pass.

---

### 6. Library Gap Detection

**Where:** A quiet section in the web UI — maybe a card on the main dashboard, or a tab in the preset browser sidebar.

**UX:** A handful of short insights that update periodically (daily, or after significant ingest events). Things like:
- "Heavy on kicks (412), light on bass (38)"
- "No acid bass samples — Big Beat Blowout preset will struggle on pad 6"
- "Lots of content at 120-130 BPM, almost nothing above 160"
- "Your minor key coverage is 3x your major key coverage"

Not alerts. Not notifications. Just observations that are there when you look.

**What the LLM does:**
- Receives: full library tag distribution (counts by type code, genre, BPM range, key), active presets and their fetch rules, recent fetch failures (pads that couldn't find good matches)
- Returns: 3-5 short insight strings

**Update frequency:** Run once daily (could piggyback on daily bank generation). Cache results. Don't re-run on every page load.

**Graceful degradation:** Section hidden if LLM unavailable. Or show basic stats without the natural language framing.

---

## Implementation Plan

### Phase 1: Foundation
- [ ] Create `scripts/llm_client.py` — single function that all integration points call. Handles: endpoint config, prompt construction, timeout (10s default), retry (1x), JSON parsing, graceful fallback.
- [ ] System prompt library — one system prompt per integration point, stored as constants or small text files. Each one includes the relevant format spec and constraints.
- [ ] Response validation — every LLM response gets validated before use. Malformed preset YAML? Discard. Nonsensical tags? Fall back to rule-based. Never surface raw LLM output without validation.

### Phase 2: High-Impact Integrations
- [ ] Preset browser vibe field (integration #1) — highest visibility, builds directly on existing vibe_generate.py
- [ ] Smart ingest tagging (integration #3) — invisible but improves everything downstream
- [ ] Thoughtful daily bank (integration #4) — enhances an existing feature with minimal new UI

### Phase 3: Refinement Integrations
- [ ] Pad editing refinement (integration #2) — requires more nuanced prompt engineering
- [ ] Library gap detection (integration #6) — needs library-wide stats aggregation
- [ ] Fetch result insights (integration #5) — start with templates, upgrade to LLM later

### Dependencies
- A local LLM endpoint must be running at `SP404_LLM_ENDPOINT`
- Recommended: a model with good instruction following and structured output (Llama 3, Mistral, etc.)
- All integrations degrade gracefully without the endpoint — ship the UI changes first, light up the LLM when it's ready

---

## Prompt Engineering Notes

A few things that will matter when writing the system prompts:

**Preset generation prompts** need to include:
- The full preset YAML format spec
- Valid type codes (KIK, SNR, HAT, CLP, PRC, BRK, BAS, SYN, GTR, KEY, PAD, VOX, SMP, FX)
- The 3-4 keywords per pad rule
- Pad layout convention (1-4 drums, 5-12 loops/melodic)

**Tag enrichment prompts** need to include:
- The existing tag vocabulary (so the LLM generates tags that match the scoring system)
- Instructions to ADD tags, never remove existing ones
- A ban on hallucinating metadata (if it doesn't know the cultural reference, skip it)

**Daily bank prompts** need:
- The user's library stats as context
- Recent activity data
- Instructions to balance familiarity and discovery
- The preset format spec

**General rules for all prompts:**
- Return JSON only, no markdown, no preamble
- Keep responses short — we're asking for structured data, not essays
- Temperature low (0.3-0.5) for structured output, slightly higher (0.6-0.7) for curator's notes
