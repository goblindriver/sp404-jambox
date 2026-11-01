import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import karaoke_drops  # noqa: E402
import karaoke_lyrics  # noqa: E402
from karaoke_lyrics import LyricLine  # noqa: E402


def _load_deck():
    spec = importlib.util.spec_from_file_location(
        "karaoke_deck", os.path.join(REPO_ROOT, "deck", "karaoke_deck.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SONG_LRC = """[ar:Test Band]
[ti:Test Song]
[offset:+500]
[00:10.50]Verse line one
[00:14.00]Verse line two
[00:18.00][01:02.00]We are the front line
[00:22.00][01:06.00]Dancing all night
[00:26.00]Second verse here
[00:30.00]Another verse line
[00:58.00]
[01:10.00]Outro <01:11.00>words
"""


class LyricsTests(unittest.TestCase):
    def test_parse_lrc_handles_offset_multistamps_and_word_timing(self):
        lines = karaoke_lyrics.parse_lrc(SONG_LRC)
        self.assertEqual(lines[0], LyricLine(10.0, "Verse line one"))  # +500ms offset = earlier
        texts = [ln.text for ln in lines]
        self.assertEqual(texts.count("We are the front line"), 2)
        self.assertIn("Outro words", texts)
        self.assertIn("", texts)  # instrumental gap kept
        self.assertEqual([ln.t for ln in lines], sorted(ln.t for ln in lines))

    def test_find_choruses_returns_repeated_blocks(self):
        lines = karaoke_lyrics.parse_lrc(SONG_LRC)
        choruses = karaoke_lyrics.find_choruses(lines)
        self.assertEqual(len(choruses), 2)
        self.assertAlmostEqual(choruses[0][0], 17.5)
        self.assertAlmostEqual(choruses[1][0], 61.5)

    def test_render_ass_is_43_and_has_countdown(self):
        lines = karaoke_lyrics.parse_lrc(SONG_LRC)
        ass = karaoke_lyrics.render_ass(lines, title="Test Band - Test Song", duration_s=80)
        self.assertIn("PlayResX: 640", ass)
        self.assertIn("PlayResY: 480", ass)
        self.assertIn("Verse line one", ass)
        self.assertIn("● ● ●", ass)
        self.assertNotIn("{We", ass)  # braces in lyrics never leak as override tags

    def test_ass_escapes_braces(self):
        ass = karaoke_lyrics.render_ass([LyricLine(1.0, "hey {there}")], duration_s=5, countdown=False)
        self.assertIn("hey (there)", ass)

    def test_format_lrc_roundtrip(self):
        lines = karaoke_lyrics.parse_lrc(SONG_LRC)
        again = karaoke_lyrics.parse_lrc(karaoke_lyrics.format_lrc(lines))
        self.assertEqual([ln.text for ln in again], [ln.text for ln in lines])

    def test_fetch_lrclib_prefers_get_then_search_by_duration(self):
        class Resp:
            def __init__(self, code, data):
                self.status_code, self._data = code, data

            def json(self):
                return self._data

        calls = []

        class Session:
            def get(self, url, params=None, headers=None, timeout=None):
                calls.append(url)
                if url.endswith("/get"):
                    return Resp(404, {})
                return Resp(200, [
                    {"id": 1, "duration": 300, "syncedLyrics": "[00:01.00]far", "plainLyrics": "far"},
                    {"id": 2, "duration": 181, "syncedLyrics": "[00:01.00]close", "plainLyrics": "close"},
                    {"id": 3, "duration": 180, "instrumental": True},
                ])

        hit = karaoke_lyrics.fetch_lrclib("A", "B", duration_s=180, session=Session())
        self.assertEqual(hit["id"], 2)
        self.assertTrue(calls[0].endswith("/get") and calls[1].endswith("/search"))

    def test_find_lyrics_uses_sidecar_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, "song.flac")
            open(audio, "wb").close()
            with open(os.path.join(tmp, "song.lrc"), "w") as fh:
                fh.write("[00:05.00]hello\n")
            lines, source, _ = karaoke_lyrics.find_lyrics(audio, "A", "B", online=False)
            self.assertEqual(source, "sidecar")
            self.assertEqual(lines[0].text, "hello")


class DropsTests(unittest.TestCase):
    def test_pad_to_midi_matches_manual_table(self):
        self.assertEqual(karaoke_drops.pad_to_midi("A", 1), (1, 47))
        self.assertEqual(karaoke_drops.pad_to_midi("B", 1), (1, 59))
        self.assertEqual(karaoke_drops.pad_to_midi("E", 12), (1, 106))
        self.assertEqual(karaoke_drops.pad_to_midi("F", 1), (2, 47))
        self.assertEqual(karaoke_drops.pad_to_midi("J", 12, base_channel=10), (11, 106))
        with self.assertRaises(ValueError):
            karaoke_drops.pad_to_midi("K", 1)
        with self.assertRaises(ValueError):
            karaoke_drops.pad_to_midi("F", 1, base_channel=16)

    def test_midi_roundtrip_all_pads(self):
        for bank in karaoke_drops.BANKS:
            for pad in range(1, 13):
                ch, note = karaoke_drops.pad_to_midi(bank, pad, 3)
                self.assertEqual(karaoke_drops.midi_to_pad(ch, note, 3), (bank, pad))

    def test_snap_to_bar(self):
        # 120 bpm → 2s bars, grid starts at 0.5s
        self.assertEqual(karaoke_drops.snap_to_bar(17.4, 120, 0.5), 16.5)
        self.assertEqual(karaoke_drops.snap_to_bar(17.6, 120, 0.5), 18.5)

    def test_draft_lands_on_chorus_downbeats(self):
        drops = karaoke_drops.draft_drop_sheet(
            duration_s=200, bpm=120, first_beat_s=0.5,
            choruses=[(40.6, 60), (100.4, 120), (160.5, 180)],
            first_vocal_s=20, last_vocal_s=185, energy="high")
        labels = [d["label"] for d in drops]
        self.assertTrue(any("crowd pop" in lb for lb in labels))
        self.assertTrue(any(lb.startswith("riser") for lb in labels))
        horn = next(d for d in drops if d["label"] == "air horn: chorus 1")
        self.assertEqual(horn["t"], 40.5)
        self.assertEqual(horn["pad"], karaoke_drops.DROP_PADS["airhorn"])
        self.assertTrue(any(d["label"] == "choir stab: chorus 2" for d in drops))
        self.assertTrue(any(d["label"] == "impact: final chorus" for d in drops))
        self.assertEqual(drops[-1]["pad"], karaoke_drops.DROP_PADS["applause"])
        ts = [d["t"] for d in drops]
        self.assertEqual(ts, sorted(ts))
        self.assertTrue(all(b - a >= karaoke_drops.MIN_GAP_S for a, b in zip(ts, ts[1:])))

    def test_gentle_songs_get_no_air_horns(self):
        drops = karaoke_drops.draft_drop_sheet(duration_s=200, bpm=80, choruses=[(40, 60), (100, 120), (150, 170)],
                                               first_vocal_s=10, last_vocal_s=180, energy="low")
        self.assertFalse(any(d["pad"] == karaoke_drops.DROP_PADS["airhorn"] for d in drops))

    def test_no_lyrics_falls_back_to_periodic_hype(self):
        drops = karaoke_drops.draft_drop_sheet(duration_s=240, bpm=120, first_beat_s=0.0)
        self.assertTrue(any("no lyric map" in d["label"] for d in drops))

    def test_validate_drops(self):
        clean = karaoke_drops.validate_drops([{"t": "5", "pad": 3, "vel": 300}, {"t": 1, "bank": "j", "pad": 12}])
        self.assertEqual(clean[0]["bank"], "J")
        self.assertEqual(clean[1]["vel"], 127)
        with self.assertRaises(ValueError):
            karaoke_drops.validate_drops([{"t": 1, "pad": 13}])

    def test_drop_pads_match_karaoke_drops_preset(self):
        import preset_utils
        preset = preset_utils.load_preset("utility/karaoke-drops")
        pads = preset["pads"]
        self.assertIn("airhorn", pads[karaoke_drops.DROP_PADS["airhorn"]])
        self.assertIn("applause", pads[karaoke_drops.DROP_PADS["applause"]])
        self.assertIn("riser", pads[karaoke_drops.DROP_PADS["riser"]])
        self.assertTrue(all(desc.endswith(("one-shot", "transition")) for desc in pads.values()))


class PrepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["SP404_KARAOKE_DIR"] = os.path.join(self.tmp.name, "Karaoke")
        self.addCleanup(os.environ.pop, "SP404_KARAOKE_DIR", None)
        import karaoke_prep
        self.prep = karaoke_prep
        self.audio = os.path.join(self.tmp.name, "src", "Home Front - Test.flac")
        os.makedirs(os.path.dirname(self.audio))
        open(self.audio, "wb").close()
        with open(os.path.splitext(self.audio)[0] + ".lrc", "w") as fh:
            fh.write(SONG_LRC)

    def _fake_separator(self, audio_path, song_dir, model):
        for name in ("backing.flac", "guide.flac"):
            open(os.path.join(song_dir, name), "wb").close()

    def test_prep_song_writes_package_and_index(self):
        out = os.path.join(self.tmp.name, "out")
        with mock.patch.object(self.prep, "analyze",
                               return_value={"bpm": 150.0, "first_beat_s": 0.4, "key": "Am", "duration_s": 80.0}):
            song = self.prep.prep_song(
                {"file_path": self.audio, "artist": "Home Front", "title": "Test/Song",
                 "moods": ["Energetic"], "styles": ["Post-Punk", "Punk"]},
                out_root=out, separator=self._fake_separator, online=False, log=lambda *_: None)
        song_dir = os.path.join(out, "Home Front - Test_Song")
        for name in ("song.json", "lyrics.lrc", "lyrics.ass", "backing.flac"):
            self.assertTrue(os.path.isfile(os.path.join(song_dir, name)), name)
        self.assertEqual(song["lyrics_source"], "sidecar")
        self.assertEqual(song["energy"], "high")
        self.assertEqual(song["preset"], "genre/synth-punk-pogo")
        self.assertEqual(len(song["choruses"]), 2)
        self.assertTrue(song["drops"])

        songs = self.prep.rebuild_index(out)
        self.assertEqual(len(songs), 1)
        self.assertTrue(songs[0]["has_guide"])

    def test_locked_drops_survive_refresh(self):
        out = os.path.join(self.tmp.name, "out")
        kwargs = dict(out_root=out, separator=self._fake_separator, online=False, log=lambda *_: None)
        meta = {"file_path": self.audio, "artist": "A", "title": "B"}
        with mock.patch.object(self.prep, "analyze",
                               return_value={"bpm": 120.0, "first_beat_s": 0.0, "key": None, "duration_s": 80.0}):
            self.prep.prep_song(meta, **kwargs)
            path = os.path.join(out, "A - B", "song.json")
            with open(path) as fh:
                data = json.load(fh)
            data["drops"] = [{"t": 3.0, "bank": "B", "pad": 1, "vel": 90, "label": "mine"}]
            data["drops_locked"] = True
            with open(path, "w") as fh:
                json.dump(data, fh)
            song = self.prep.prep_song(meta, refresh=True, **kwargs)
        self.assertEqual(song["drops"][0]["label"], "mine")
        self.assertTrue(song["drops_locked"])

    def test_suggest_preset_and_dirname(self):
        self.assertEqual(self.prep.suggest_preset(["Synth Punk"], []), "genre/synth-punk-pogo")
        self.assertEqual(self.prep.suggest_preset(["Hardcore Punk"], []), "genre/riot-mode")
        self.assertEqual(self.prep.suggest_preset(["New Wave"], []), "genre/synth-punk-pogo")
        self.assertEqual(self.prep.suggest_preset(["Heavy Metal"]), "genre/karaoke-metal")
        self.assertIsNone(self.prep.suggest_preset([], []))
        self.assertEqual(self.prep.safe_dirname('AC/DC', 'What?: "x"'), "AC_DC - What__ _x_")


class DeckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deck = _load_deck()

    def test_ticks_due(self):
        d = self.deck
        self.assertEqual(d.ticks_due(0.4, 120, 0.5), 0)       # before first downbeat
        self.assertEqual(d.ticks_due(0.5, 120, 0.5), 1)       # Start + first tick
        self.assertEqual(d.ticks_due(1.0, 120, 0.5), 25)      # one beat later = 24 more
        self.assertEqual(d.ticks_due(5.0, None), 0)

    def test_song_position_pointer(self):
        self.assertEqual(self.deck.song_position_pointer(2.5, 120, 0.5), 16)  # 4 beats = 16 sixteenths

    def test_drops_between(self):
        drops = [{"t": 1.0}, {"t": 2.0}, {"t": 3.0}]
        self.assertEqual(self.deck.drops_between(drops, 1.0, 2.5), [{"t": 2.0}])
        self.assertEqual(self.deck.drops_between(drops, 3.0, 1.0), [])
        self.assertEqual(self.deck.drops_between(drops, None, 5.0), [])

    def test_mpv_args_and_guide_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("backing.flac", "lyrics.ass", "guide.flac"):
                open(os.path.join(tmp, name), "wb").close()
            args = self.deck.build_mpv_args(tmp, {"artist": "A", "title": "B"},
                                            audio_device="wasapi/{m6}", sub_delay=0.1)
            joined = " ".join(args)
            self.assertIn("--sub-files=", joined)
            self.assertIn("--audio-files=", joined)
            self.assertIn("--audio-device=wasapi/{m6}", joined)
            self.assertIn("--sub-delay=0.1", joined)
            self.assertNotIn("--cover-art-files", joined)
        self.assertEqual(self.deck.guide_graph(None, True), "")
        self.assertIn("volume=-18dB", self.deck.guide_graph(-18, False))
        self.assertIn("[vid1]null[vo]", self.deck.guide_graph(-9, True))
        self.assertAlmostEqual(self.deck.pitch_scale(12), 2.0)


class TypeCodeAliasTests(unittest.TestCase):
    def test_legacy_type_codes_alias_to_canonical(self):
        import fetch_samples
        parsed = fetch_samples.parse_pad_query("TOM floor deep thunder roll one-shot")
        self.assertEqual(parsed["type_code"], "PRC")
        self.assertIn("tom", parsed["keywords"])
        self.assertEqual(fetch_samples.parse_pad_query("HHT bright open one-shot")["type_code"], "HAT")
        self.assertEqual(fetch_samples.parse_pad_query("CHR epic choir loop")["type_code"], "VOX")
        # lowercase words stay keywords
        parsed = fetch_samples.parse_pad_query("GTR ska bass loop")
        self.assertEqual(parsed["type_code"], "GTR")
        self.assertIn("ska", parsed["keywords"])

    def test_every_preset_pad_resolves_to_known_type_code(self):
        import glob
        import yaml
        import fetch_samples
        from tag_vocab import TYPE_CODES
        for path in glob.glob(os.path.join(REPO_ROOT, "presets", "**", "*.yaml"), recursive=True):
            with open(path) as fh:
                preset = yaml.safe_load(fh) or {}
            for pad, desc in (preset.get("pads") or {}).items():
                if not desc:
                    continue
                tc = fetch_samples.parse_pad_query(desc)["type_code"]
                self.assertIn(tc, TYPE_CODES, f"{os.path.relpath(path, REPO_ROOT)} pad {pad}: {desc!r}")


if __name__ == "__main__":
    unittest.main()
