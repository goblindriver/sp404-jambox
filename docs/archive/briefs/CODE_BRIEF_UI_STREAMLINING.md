# Code Brief: UI Streamlining — "Maximum Fun, Minimum Buttons"

## The Problem

The current UI has **41 interactive elements** on a single screen. That's a control panel, not an instrument. Every feature that got built earned its own button in the bottom bar, and now the bottom bar is doing three different jobs at once: browsing, pipeline operations, and creative actions.

The goal: strip the interface down so it feels like picking up an instrument, not configuring a dashboard. Every click should move you closer to making music.

## Current State (from screenshot review)

### Header
- `SP-404 JAMBOX` title (left)
- `SD: not connected` status (right)

### Bank Tabs
- A through J with colored status dots

### Set Row
- `SET:` label + dropdown (Default Set)
- `Save Set` button
- `Daily Bank` button

### Bank Info
- Bank name, BPM, Key, description
- Edit bank settings button (wrench icon, top-right)

### Vibe Prompt Area
- Text input: "Describe a vibe..."
- BPM input field
- Key input field
- `Suggest` button

### Pad Grid
- 12 pads (4x3), each showing: pad number, waveform, type code + keywords + playability

### Bottom Bar (11 buttons)
`? | Library | Presets | My Music | Ingest Downloads | Watch | Disk | Fetch All | Generate Pattern | Build | Deploy to SD`

---

## Proposed Changes

### Bottom Bar: 11 buttons → 3

**Keep:**

| Button | Why |
|--------|-----|
| **Browse** | Replaces Library + Presets + My Music. One button opens a sidebar panel with tabs inside. Same content, one entry point. |
| **Fetch All** | Primary creative action. Stays orange. Stays prominent. This is the "go" button. |
| **Export to SD** | Replaces Build + Deploy to SD. One button, two-step flow: format for 404 → write to card. Grayed out when SD not connected. Shows progress inline. |

**Remove from bottom bar (relocated, not deleted):**

| Button | Where it goes | Why |
|--------|---------------|-----|
| **?** (How it works) | Small `?` icon in header, top-right corner, near SD status | Used once, doesn't need prime real estate |
| **Library** | Tab inside Browse sidebar panel | |
| **Presets** | Tab inside Browse sidebar panel | |
| **My Music** | Tab inside Browse sidebar panel | |
| **Ingest Downloads** | Removed entirely from main UI. If manual ingest is ever needed, accessible from a Settings/Admin menu (gear icon in header). The watcher handles this automatically. | Redundant when watcher is running |
| **Watch** | Status indicator in header, next to SD status. Green dot + "Watching" / gray dot + "Watcher off". Click to toggle. | It's a toggle state, not an action. Same visual pattern as SD status. |
| **Disk** | Accessible from Settings/Admin menu (gear icon in header). Or: small disk usage bar in header that's just always visible — no click needed, just a glanceable indicator. | Utility, not creative |
| **Generate Pattern** | Moves to pad-level interaction (see Pad Interactions below) | More useful in context of a specific pad than as a global action |
| **Build** | Absorbed into Export to SD flow | Two steps of one process shouldn't be two buttons |

### Set Row: 3 controls → 1

**Current:** `SET: [dropdown] | Save Set | Daily Bank`

**Proposed:** `SET: [dropdown]`

- **Save Set** → becomes an option inside the dropdown: last item is "Save current as new set..." Opens a name-it dialog.
- **Daily Bank** → moves into the Browse sidebar under the Presets tab. It's a preset — it lives with presets. Could be pinned at the top of the Presets tab with a ✨ indicator and today's date.

### Vibe Prompt Area: Simplify defaults

**Current:** Text input + BPM field + Key field + Suggest button

**Proposed:** Just the text input + Suggest button by default.

- BPM and Key auto-populate from the current bank's settings
- If the user wants to override, they can include it in the natural language prompt ("...at 140 BPM in Gm") and the LLM handles it
- Or: BPM/Key fields appear as a collapsed "advanced" toggle that most users never touch
- The Suggest button could also just be hitting Enter in the text field — one less button

### Header: Add status indicators

**Proposed header layout:**
```
[SP-404 JAMBOX]                    [?] [⚙️] [● Watching] [● SD: not connected]
```

- `?` — help, small icon
- `⚙️` — settings/admin menu (contains: Disk, Ingest Downloads, Watcher toggle, any future admin tools)
- `● Watching` — green/gray dot, click to toggle watcher
- `● SD: not connected` — already exists, stays

This clusters all status/utility in the header and keeps the main workspace clean.

---

## Pad Interactions: Context Over Global

Right now, clicking a pad probably opens some kind of detail view. This is where **Generate Pattern** and other pad-specific actions should live — in context, not in the global bottom bar.

### Proposed pad click behavior:

Click a pad → expanded pad view appears (overlay or inline expansion) showing:

1. **Current sample info** — waveform, filename, tags, score explanation
2. **Audition** — play button to preview
3. **Re-fetch** — "Find something else" button, re-runs fetch for just this pad
4. **Refine** — text input: "darker" / "more acoustic" / "less busy" (LLM adjusts keywords, re-fetches)
5. **Generate Pattern** — if this pad is part of a scale mapping, generate an arp/sequence for it
6. **Swap type** — change from one-shot to loop, change type code
7. **Remove** — clear the pad

This puts all pad-level actions where they belong: on the pad. The user clicks what they want to change and gets tools for changing it. No hunting through bottom bar buttons.

### Pad right-click / long-press:
Quick actions menu: Copy, Paste, Swap with another pad, Clear.

---

## Visual Hierarchy

The current layout is roughly:
```
[Bank Tabs          ]  ← Navigation
[Set Controls       ]  ← Configuration
[Bank Info          ]  ← Context
[Vibe Prompt        ]  ← Input
[Pad Grid           ]  ← THE INSTRUMENT
[Bottom Bar         ]  ← Everything else
```

The pad grid — the actual instrument — is squeezed in the middle with configuration above and a wall of buttons below. It should feel like the center of gravity.

**Proposed:**
```
[Bank Tabs     ] [● status indicators] [? ⚙️]  ← Compact header
[SET: dropdown ] [Bank: name · BPM · Key      ]  ← One line of context
[Vibe: describe a vibe...              ] [Suggest]  ← Input
[                                               ]
[              PAD GRID (larger)                 ]  ← THE INSTRUMENT — more vertical space
[                                               ]
[Browse]            [Fetch All]        [Export to SD]  ← Three actions
```

The pad grid gets more vertical space because there's less stuff above and below it. The pads can be taller, waveforms more visible, text more readable.

---

## Summary of Changes

| Area | Before | After |
|------|--------|-------|
| Bottom bar | 11 buttons | 3 buttons |
| Set row | 3 controls | 1 dropdown |
| Vibe prompt | 4 controls | 2 controls (text + suggest) |
| Header | Title + SD status | Title + status indicators + settings + help |
| Pad interactions | Global Generate Pattern button | Pad-level contextual actions |
| Total visible controls | ~41 | ~20 (and the 12 pads are doing more) |

---

## What NOT to Change

- **Bank tabs A-J** — Core navigation, works great, the colored dots are useful
- **Pad grid layout** — 4x3 is correct for 12 pads
- **Dark theme** — Right for this kind of app
- **Waveform previews on pads** — Instantly useful visual feedback
- **Type codes on pads** — Quick read of what's on each pad
- **Vibe prompt placement** — Between bank info and pad grid is the right spot

---

## Implementation Notes

- The Browse sidebar should remember which tab (Library/Presets/My Music) was last active
- Export to SD should show a progress state: "Building..." → "Deploying..." → "Done ✓" then revert to default
- The settings gear menu should be simple — just a dropdown list, not a full settings page
- Pad click interactions can be implemented incrementally — start with the expanded view and audition, add refine/generate later
- All changes are purely frontend — no backend/API changes needed
