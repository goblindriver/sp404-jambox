# Creative Tools Reference — Automation Hooks & Integration Guide

> Compiled 2026-04-11. Premium and open-source creative software with programmable hooks,
> organized by automation depth and relevance to the Jambox pipeline.

---

## Table of Contents
1. [DAWs & Audio Production](#daws--audio-production)
2. [Visual & Motion Tools](#visual--motion-tools)
3. [Adobe Creative Suite](#adobe-creative-suite)
4. [Audio Processing & Batch Tools](#audio-processing--batch-tools)
5. [Music Coding & Synthesis](#music-coding--synthesis)
6. [macOS Automation Glue](#macos-automation-glue)
7. [Integration Recipes](#integration-recipes)

---

## DAWs & Audio Production

### Ableton Live (+ Max for Live)

**Hook type:** Python Remote Scripts, OSC, Max patching, Node.js
**Best external path:** AbletonOSC + pylive

**Setup:**
```bash
pip install pylive python-osc
```
Install [AbletonOSC](https://github.com/ideoforms/AbletonOSC) Remote Script:
- Copy to `~/Music/Ableton/User Library/Remote Scripts/`
- Enable in Preferences > Link/MIDI
- Listens on UDP 11000 (in) / 11001 (out)

**Python control via pylive:**
```python
import live

set = live.Set(scan=True)
set.tempo = 112
track = set.tracks[0]
track.volume = 0.8
track.clips[0].fire()
```

**Raw OSC from python-osc:**
```python
from pythonosc.udp_client import SimpleUDPClient
client = SimpleUDPClient("127.0.0.1", 11000)
client.send_message("/live/song/set/tempo", 120.0)
client.send_message("/live/clip/fire", [0, 2])  # track 0, clip 2
client.send_message("/live/track/set/volume", [0, 0.8])
```

**What you can control:** Transport (play/stop/tempo/metronome), tracks (volume/pan/mute/solo/sends), clips (fire/stop/create/set notes), devices and parameters, scenes, cue points.

**Max for Live / Node for Max:** Requires Live Suite ($749) or add-on. Embeds Max/MSP patching + Node.js runtime inside Live. Build custom audio/MIDI devices with full LOM access. Node for Max can use npm packages, run web servers, do file I/O.

**Limitations:** No CLI/headless mode. No batch rendering. Export requires GUI automation or manual trigger.

**Key resources:**
- [AbletonOSC](https://github.com/ideoforms/AbletonOSC) — OSC bridge Remote Script
- [pylive](https://github.com/ideoforms/pylive) — Pythonic wrapper
- [ableton-js](https://github.com/leolabs/ableton-js) — Node.js/TypeScript control
- [live_rpyc](https://github.com/lucianoiam/live_rpyc) — RPyC bridge for full LOM from external Python
- [TerminalDAW](https://github.com/JIKASSA/terminaldaw) — Terminal → Max for Live → LOM

---

### Reaper + ReaScript

**Hook type:** Python, Lua, EEL scripting; OSC; CLI batch render
**Best external path:** reapy (Python via TCP bridge)

**Setup:**
```bash
pip install python-reapy
```
Enable Python in REAPER: Preferences > Plug-ins > ReaScript → point to:
`/Library/Frameworks/Python.framework/Versions/3.11/lib/libpython3.11.dylib`

Enable reapy companion action inside REAPER (opens TCP bridge on `localhost:2306`).

**External Python via reapy:**
```python
import reapy
from pathlib import Path

project = reapy.Project()
track = project.add_track(name="Batch Import")

for wav in sorted(Path("~/samples").expanduser().glob("*.wav")):
    item = track.add_item()
    item.add_source(str(wav))

# Add FX
reapy.reascript_api.TrackFX_AddByName(track.id, "VST: ReaEQ", False, -1)

# Render
reapy.perform_action(42230)  # File: Render project
```

**CLI batch rendering:**
```bash
/Applications/REAPER.app/Contents/MacOS/REAPER -renderproject /path/to/project.RPP
```
Render presets stored in `reaper-render.ini`.

**OSC control:**
Enable in Preferences > Control/OSC/Web > Add > OSC. Send from Python:
```python
from pythonosc.udp_client import SimpleUDPClient
client = SimpleUDPClient("127.0.0.1", 8000)
client.send_message("/track/1/volume", 0.75)
client.send_message("/action/42230", 1)  # trigger render
```

**Key API surface (~1,400 functions):**
- `RPR_InsertMedia(file, mode)` — insert audio
- `RPR_SetMediaItemInfo_Value(item, "D_VOL", val)` — item gain
- `RPR_TrackFX_AddByName(track, "VST: PluginName", False, -1)` — add FX
- `RPR_Main_OnCommand(cmdId, 0)` — trigger any action

**SWS Extensions:** +900 actions. Install from sws-extension.org. Adds region/marker management, batch item operations, envelope tools.

**macOS paths:**
- App: `/Applications/REAPER.app/`
- Config/scripts: `~/Library/Application Support/REAPER/`
- SWS: `~/Library/Application Support/REAPER/UserPlugins/`

---

## Visual & Motion Tools

### DaVinci Resolve (Studio)

**Hook type:** Python & Lua API, Fusion scripting, CLI render (Studio only)
**Best path:** External Python script talking to running Resolve instance

**Setup:**
```python
import sys
sys.path.append("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
```

**Object hierarchy:**
```
Resolve → ProjectManager → Project → MediaPool / Timeline
                                       ↓            ↓
                                    MediaPoolItem   TimelineItem → Fusion Comp
```

**Key operations:**
```python
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager()
project = pm.GetCurrentProject()
mp = project.GetMediaPool()

# Import media
mp.ImportMedia(["/path/to/clip1.mov", "/path/to/clip2.wav"])

# Create timeline from clips
folder = mp.GetRootFolder()
items = folder.GetClipList()
mp.CreateTimelineFromClips("My Timeline", items)

# Batch render
timeline = project.GetCurrentTimeline()
project.SetCurrentRenderFormatAndCodec("mp4", "H264")
project.SetRenderSettings({"TargetDir": "/tmp/renders", "CustomName": "output"})
project.AddRenderJob()
project.StartRendering()
```

**CLI headless (Studio only):**
```bash
"/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/MacOS/DaVinci Resolve" -nogui
```
Then connect via scripting API from external Python.

**Fusion scripting (inside timeline items):**
```python
item = timeline.GetCurrentVideoItem()
comp = item.GetFusionCompByIndex(1)
comp.Execute("AddTool('Background')")  # Lua in Fusion context
```

**Built-in console:** Workspace > Console — Python/Lua tabs, `resolve` object pre-bound.

**Free vs Studio:** Both have full scripting API. Studio adds `-nogui` headless and Neural Engine effects.

**Docs:** Ship as `README.txt` in the Developer folder, not online.

---

### Blender (bpy)

**Hook type:** Full Python API, headless CLI rendering
**Best path:** `blender --background --python script.py`

**CLI headless:**
```bash
# Render animation
/Applications/Blender.app/Contents/MacOS/Blender --background project.blend \
  --render-output /tmp/frames/#### --render-format PNG \
  --frame-start 1 --frame-end 250 --render-anim

# Single frame (album art)
/Applications/Blender.app/Contents/MacOS/Blender --background project.blend \
  --render-output /tmp/cover.png --render-frame 1
```

**Audio-driven animation (bake audio to F-curves):**
```python
import bpy

scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, 250

bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
cube = bpy.context.active_object
cube.keyframe_insert(data_path="scale", frame=1)

# Bake sound to F-curve — drives Z scale from audio amplitude
area = [a for a in bpy.context.screen.areas if a.type == 'GRAPH_EDITOR'][0]
with bpy.context.temp_override(area=area):
    bpy.ops.graph.sound_bake(
        filepath="/path/to/track.wav",
        low=80, high=500  # frequency band in Hz
    )
```

**Geometry Nodes (procedural, data-driven):**
```python
mod = cube.modifiers.new(name="GeoNodes", type='NODES')
mod.node_group = bpy.data.node_groups["MyVisualizerNodes"]
mod["Input_2"] = 3.5  # drive input per-frame from audio data
```

**Compositor (post-processing):**
```python
scene.use_nodes = True
tree = scene.node_tree
glare = tree.nodes.new('CompositorNodeGlare')
glare.glare_type = 'FOG_GLOW'
glare.threshold = 0.8
tree.links.new(tree.nodes["Render Layers"].outputs[0], glare.inputs[0])
tree.links.new(glare.outputs[0], tree.nodes["Composite"].inputs[0])
```

**Video output with codec:**
```python
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.filepath = "/tmp/visualizer.mp4"
bpy.ops.render.render(animation=True)
```

**Batch album art variations:**
```python
import bpy, random
for i in range(10):
    mat = bpy.data.materials["CoverMaterial"]
    mat.node_tree.nodes["Hue"].inputs[0].default_value = random.uniform(0, 1)
    bpy.context.scene.render.filepath = f"/tmp/cover_v{i:02d}.png"
    bpy.ops.render.render(write_still=True)
```

**Note:** Blender ships its own Python 3.11. External packages need `pip install --target` into Blender's site-packages.

---

### TouchDesigner

**Hook type:** Embedded Python 3.11, OSC/MIDI input, GLSL shaders
**Best path:** OSC bridge from DAW/Python → audio-reactive visuals

**Python in TD:**
Scripts live in Script CHOPs/SOPs/DATs, Extensions (classes on components), and Callbacks.
Access nodes: `op('audioSpectrum1')['chan1']` reads a channel value.

**Audio-reactive visual chain:**
```
Audio Device In CHOP → Audio Spectrum CHOP (FFT) → Math CHOP (scale)
  → Filter CHOP (smooth) → drive geometry/shader/Noise params
```
- `Analyze CHOP` extracts RMS/peak per band
- `Feedback TOP` creates trailing/echo effects
- `GLSL TOP` for custom fragment shaders driven by CHOP data

**OSC input from Python:**
```python
from pythonosc.udp_client import SimpleUDPClient
client = SimpleUDPClient("127.0.0.1", 7000)  # TD's OSC In CHOP port
client.send_message("/audio/bass", 0.85)
client.send_message("/bank/energy", "high")
```
TD receives via `OSC In CHOP` on configurable UDP port.

**MIDI input:** `MIDI In CHOP` from hardware or IAC virtual MIDI buses on macOS.

**Render output:**
- `Movie File Out TOP` → H.264/ProRes/image sequences
- `Window COMP` → fullscreen on secondary displays
- `Syphon Out TOP` → frame sharing to other macOS apps
- NDI Out supported

**Licensing:** Non-commercial = free (1280x1280 output limit). Commercial ~$600/year.
**Requirements:** macOS Metal (no CUDA). Apple Silicon native. 8+ GB RAM.

---

## Adobe Creative Suite

### After Effects

**Best automation path. True headless CLI rendering.**

**aerender CLI:**
```bash
/Applications/Adobe\ After\ Effects\ 2025/aerender \
  -project /path/to/project.aep \
  -comp "Main Comp" \
  -output /path/to/output.mov \
  -RStemplate "Best Settings" \
  -OMtemplate "Lossless" \
  -s 1 -e 250  # start/end frames
  -mp  # multiprocessing
```
Call from Python via `subprocess.run()`. No GUI needed.

**ExtendScript (in-app):**
Scripts in `/Applications/Adobe After Effects 2025/Scripts/`
```javascript
// template-swap.jsx
var comp = app.project.item(1);
var textLayer = comp.layer("Title");
textLayer.property("Source Text").setValue("NEW TITLE");
```

**Expressions (JS on any property):**
```javascript
// Audio-reactive scale
thisComp.layer("Audio").effect("Both Channels")("Slider") * [1,1]
```

**CEP Panels:** HTML/JS panels in `~/Library/Application Support/Adobe/CEP/extensions/`.
Enable unsigned: `defaults write com.adobe.CSXS.12 PlayerDebugMode 1`

---

### Photoshop

**ExtendScript + osascript bridge from Python.**

Scripts in `/Applications/Adobe Photoshop 2025/Presets/Scripts/`

**Batch resize example (.jsx):**
```javascript
var folder = Folder.selectDialog("Pick folder");
var files = folder.getFiles(/\.(jpg|png|tif)$/i);
for (var i = 0; i < files.length; i++) {
    var doc = app.open(files[i]);
    doc.resizeImage(UnitValue(1920,"px"), null, null, ResampleMethod.BICUBIC);
    doc.saveAs(files[i], new JPEGSaveOptions(), true);
    doc.close(SaveOptions.DONOTSAVECHANGES);
}
```

**Trigger from Python:**
```python
import subprocess
subprocess.run(["osascript", "-e",
    'tell application "Adobe Photoshop 2025" to do javascript file "/path/to/script.jsx"'])
```

**Generator:** Name a layer `my-asset.png` → Photoshop auto-exports on save.

**UXP (modern JS plugins):** Plugins in `~/Library/Application Support/Adobe/UXP/PluginsStorage/`. More sandboxed than ExtendScript.

**No headless mode.** Requires app running.

---

### Premiere Pro

**Weakest scripting of the three.** ExtendScript in `/Applications/Adobe Premiere Pro 2025/Scripts/`.

```javascript
var seq = app.project.activeSequence;
var preset = "/path/to/export-preset.epr";
seq.exportAsMediaDirect(preset, "/output/video.mp4", 1);
```

Limited timeline manipulation. No fine-grained effect control. No CLI. For truly headless encoding, use ffmpeg.

---

## Audio Processing & Batch Tools

### SoX (Sound eXchange) — RECOMMENDED

**The audio CLI swiss army knife. Pipeline-native.**

```bash
brew install sox
```

**Key commands for sample library work:**
```bash
# Peak normalize
sox input.flac output.flac gain -n

# EBU loudness normalize
sox input.flac output.flac loudness

# Trim leading/trailing silence
sox input.flac output.flac silence 1 0.01 -50d reverse silence 1 0.01 -50d reverse

# Fade in/out (5ms)
sox input.flac output.flac fade t 0.005 0 0.005

# Stats (peak, RMS, DC offset)
sox input.flac -n stat

# Effect chain
sox in.flac out.flac norm -1 fade t 0.003 0 0.003 rate 44100

# Convert sample rate + bit depth
sox input.flac -r 44100 -b 16 output.wav
```

Call from Python via `subprocess`. Zero state, pure pipeline tool.

### iZotope RX

**GUI-only batch processor.** No CLI, no scripting API. Chain modules (De-noise, De-click, De-hum, Normalize) and save as presets. Good for surgical manual fixes on flagged files. Not automatable at scale for 30K files.

**Best use:** Review files flagged by quality_score system in smart retag.

### Audacity

Macro system + `mod-script-pipe` named-pipe interface. Unreliable at scale, poorly documented, requires GUI running. **Not recommended for batch pipeline.**

---

## Music Coding & Synthesis

### SuperCollider — Best Python Bridge

**A programming language for audio.** sclang (language) + scsynth (audio server).
The server speaks OSC natively — Python controls it directly.

```python
from pythonosc.udp_client import SimpleUDPClient
sc = SimpleUDPClient("127.0.0.1", 57110)  # scsynth default port

# Trigger a synth
sc.send_message("/s_new", ["default", 1000, 0, 0, "freq", 440, "amp", 0.5])

# Free it
sc.send_message("/n_free", [1000])
```

**Pattern library** (Pbind, Pseq, Prand) for generative sequencing. Sample granulation, live effects, buffer manipulation are first-class. Free and open-source.

### Pure Data (Pd) — Embeddable in Python

Free, open-source Max/MSP alternative. Same visual patching paradigm.

**libpd** embeds the Pd engine as a C library. Python bindings: `pylibpd`.
Run Pd audio processing directly inside Python scripts. No licensing cost.

External control via OSC, FUDI protocol, or netsend/netreceive objects.

### Max/MSP

Visual audio programming. $399 perpetual or $10/mo.

- **Node for Max:** Full Node.js runtime inside patches. npm packages, file I/O, network.
- **Max for Live:** Extends Ableton (requires Suite or add-on).
- Python control via `python-osc` → Max's `udpreceive` objects.

### Vital Synth — JSON Presets!

Presets are `.vital` files = **plain JSON**. Fully readable and writable from Python.

```python
import json

with open("preset.vital") as f:
    preset = json.load(f)

# Modify filter cutoff
preset["settings"]["filter_1_cutoff"] = 80.0

# Generate wavetables programmatically as raw audio frames
# Write modified preset
with open("new_preset.vital", "w") as f:
    json.dump(preset, f)
```

Wavetables can be generated as raw audio and imported. Free tier available; $25/$80 for Plus/Pro.

### Sonic Pi

Ruby-based live coding. Accepts OSC on `/run-code` endpoint (execute code remotely from Python). Sends MIDI to hardware. Free. Good for quick generative ideas.

### VCV Rack

Virtual Eurorack. C++ module SDK. MIDI I/O but limited external automation (no native OSC). Community OSC modules exist. Free version available.

---

## macOS Automation Glue

### Keyboard Maestro — RECOMMENDED Orchestrator

**Triggers:** Hotkeys, folder watch, USB device connect (fires when SD card mounts!), time schedule, app-specific activation, MIDI, remote web trigger.

**Shell integration:**
```
Execute Shell Script action → .venv/bin/python scripts/fetch_samples.py
```
Captures stdout into KM variables. Full environment access.

**Practical recipe:** USB trigger detects SD card mount → run build pipeline → copy to card → system notification.

**Flow control:** Conditionals, loops, regex, variables, UI scripting for apps lacking AppleScript.

### Hammerspoon — Lua-based Hackable Glue

Config: `~/.hammerspoon/init.lua`. Reloads instantly.

**Key modules:**
- `hs.pathwatcher` — monitor directories (alternative to Python watchdog)
- `hs.audiodevice` — control output routing (switch to SP-404 audio interface)
- `hs.httpserver` — local HTTP endpoint other tools can POST to
- `hs.window` — tile windows (ComfyUI, terminal, browser)

### BetterTouchTool — Named Triggers

Define automation, call from CLI:
```bash
open "btt://trigger_named/?trigger_name=run_pipeline"
```
Python scripts can trigger BTT automations. Also window snapping, clipboard management.

### AppleScript / osascript

The inter-app bridge. From Python:
```python
import subprocess
subprocess.run(["osascript", "-e", 'tell application "Finder" to open folder "..."'])
```

**Apps with strong dictionaries:** Finder, Music.app, Photos, Preview, Safari, Mail, System Events (UI scripting any app).

### Apple Shortcuts

"Run Shell Script" action executes terminal commands. Siri-triggered: "Hey Siri, ingest downloads". No folder-watch or USB triggers. Lightweight entry point to Python scripts.

### tmux

Essential for long-running pipelines. External tools trigger work in persistent sessions:
```bash
tmux send-keys -t jambox:0 'python scripts/smart_retag.py' Enter
```

---

## Integration Recipes

### Recipe 1: SD Card Auto-Deploy
**Tools:** Keyboard Maestro + Jambox pipeline
```
KM USB Trigger (SD card mount detected)
  → Execute Shell: cd /path/to/jambox && .venv/bin/python scripts/fetch_samples.py
  → Execute Shell: .venv/bin/python scripts/gen_padinfo.py
  → Execute Shell: bash scripts/copy_to_sd.sh
  → Display Notification: "SP-404 card ready!"
```

### Recipe 2: Sample Audition in Reaper
**Tools:** reapy + Jambox fetch
```python
# After fetch_samples.py populates a bank, load into Reaper for preview
import reapy
from pathlib import Path

project = reapy.Project()
bank_dir = Path("/Volumes/SP-404SX/ROLAND/SP-404SX/SMPL/")
track = project.add_track(name="Bank G Preview")
for wav in sorted(bank_dir.glob("G*.WAV")):
    item = track.add_item()
    item.add_source(str(wav))
```

### Recipe 3: Beat Video Pipeline
**Tools:** DaVinci Resolve API + Blender + ffmpeg
```python
# 1. Blender: generate audio-reactive visualizer
subprocess.run([
    "/Applications/Blender.app/Contents/MacOS/Blender",
    "--background", "visualizer_template.blend",
    "--python", "render_viz.py"
])

# 2. DaVinci Resolve: composite with overlays
import DaVinciResolveScript as dvr
resolve = dvr.scriptapp("Resolve")
# ... import media, create timeline, render

# 3. ffmpeg: final encode for social
subprocess.run(["ffmpeg", "-i", "raw.mov", "-c:v", "libx264", "-preset", "slow", "final.mp4"])
```

### Recipe 4: Live Visuals for SP-404 Performance
**Tools:** TouchDesigner + OSC + SP-404 audio out
```
SP-404 audio output → Audio Device In CHOP (TD)
  → Audio Spectrum → Math → Filter
  → Drive geometry scale, shader colors, particle density
  → Window COMP fullscreen on projector
```
Optionally send bank/pad metadata from Jambox web UI → OSC → TD for bank-aware visuals.

### Recipe 5: Generative Preset Sounds via SuperCollider
**Tools:** SuperCollider + python-osc + Jambox pipeline
```python
from pythonosc.udp_client import SimpleUDPClient
sc = SimpleUDPClient("127.0.0.1", 57110)

# Generate a one-shot with specific characteristics
sc.send_message("/s_new", ["percSynth", 1000, 0, 0,
    "freq", 60, "decay", 0.3, "noise", 0.1])
# Record output, convert to WAV, inject RLND chunk, deploy to pad
```

### Recipe 6: Programmatic Vital Wavetables from Samples
**Tools:** Vital + Python + librosa
```python
import librosa, json, numpy as np

# Extract spectral frame from a sample
y, sr = librosa.load("sample.flac", sr=44100)
frame = np.fft.rfft(y[:2048])  # one wavetable frame

# Write into Vital preset JSON
with open("template.vital") as f:
    preset = json.load(f)
preset["settings"]["osc_1_wave_data"] = frame.tolist()  # simplified
with open("from_sample.vital", "w") as f:
    json.dump(preset, f)
```

### Recipe 7: Hammerspoon Window Workspace
**Tools:** Hammerspoon
```lua
-- ~/.hammerspoon/init.lua
hs.hotkey.bind({"cmd", "shift"}, "J", function()
    -- Jambox workspace: web UI left, terminal right, ComfyUI bottom
    local webUI = hs.application.find("Safari")
    local term = hs.application.find("Terminal")
    local screen = hs.screen.mainScreen():frame()

    if webUI then webUI:mainWindow():setFrame({x=0, y=0, w=screen.w/2, h=screen.h}) end
    if term then term:mainWindow():setFrame({x=screen.w/2, y=0, w=screen.w/2, h=screen.h/2}) end
end)
```

---

## Quick Reference: What Talks to What

```
                    ┌─────────────┐
                    │   Python    │
                    │  (Jambox)   │
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
     subprocess        python-osc       reapy TCP
          │                │                │
    ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
    │  ffmpeg   │   │  Ableton  │   │  Reaper   │
    │  sox      │   │  (OSC)    │   │  (bridge) │
    │  blender  │   │           │   │           │
    │  aerender │   │  Touch    │   └───────────┘
    │  osascript│   │  Designer │
    └───────────┘   │  (OSC)    │
                    │           │
                    │  Super    │
                    │  Collider │
                    │  (OSC)    │
                    └───────────┘

    KM/Hammerspoon/BTT = trigger layer (USB, hotkey, folder watch)
    tmux = persistent session layer
    DaVinci Resolve = IPC to running instance (no CLI in Free)
```

---

## Install Checklist

| Tool | Install | Cost | Priority |
|------|---------|------|----------|
| SoX | `brew install sox` | Free | HIGH — batch audio processing |
| python-osc | `pip install python-osc` | Free | HIGH — OSC bridge to everything |
| reapy | `pip install python-reapy` | Free | HIGH — external Reaper control |
| pylive | `pip install pylive` | Free | MED — Ableton control |
| Blender | blender.org | Free | MED — visualizers, album art |
| SuperCollider | supercollider.github.io | Free | MED — generative audio |
| TouchDesigner | derivative.ca | Free (non-com) | MED — live visuals |
| DaVinci Resolve | blackmagicdesign.com | Free / $295 Studio | MED — video pipeline |
| Keyboard Maestro | keyboardmaestro.com | $36 | HIGH — orchestration glue |
| Hammerspoon | hammerspoon.org | Free | MED — window/audio/watcher |
| Vital | vital.audio | Free / $25 / $80 | LOW — wavetable synthesis |
| Pure Data | puredata.info | Free | LOW — embeddable audio |
| Reaper | reaper.fm | $60 | HAVE? — deepest DAW scripting |
| Ableton Live | ableton.com | $99-749 | HAVE? — AbletonOSC is killer |
| Adobe CC | adobe.com | Subscription | HAVE — aerender is gold |
