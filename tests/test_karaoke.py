import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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

    def test_enhanced_lrc_word_times_parse_and_roundtrip(self):
        lines = karaoke_lyrics.parse_lrc(
            "[offset:+500]\n[00:10.50]<00:10.50>Seen <00:11.20>my <00:11.60>share\n"
            "[00:20.00][00:40.00]Chorus <00:21.00>twice\n")
        self.assertEqual(lines[0], LyricLine(10.0, "Seen my share", ((10.0, "Seen"), (10.7, "my"), (11.1, "share"))))
        self.assertEqual((lines[1].text, lines[1].words), ("Chorus twice", ()))  # absolute stamps, sung twice
        again = karaoke_lyrics.parse_lrc(karaoke_lyrics.format_lrc(lines))
        self.assertEqual(again[0].words, lines[0].words)

    def test_parse_midico_groups_words_into_lines(self):
        lines = karaoke_lyrics.parse_midico(
            "[re:MidiCo]\n[00:00.980]1:/Seen \n[00:01.720]1:my \n[00:02.100]1:share\n"
            "[00:04.000]1:/Broken \n[00:04.860]1:halos\n")
        self.assertEqual([ln.text for ln in lines], ["Seen my share", "Broken halos"])
        self.assertEqual(lines[0].t, 0.98)
        self.assertEqual(lines[1].words, ((4.0, "Broken"), (4.86, "halos")))

    def test_word_error_rate(self):
        ref = karaoke_lyrics.lyric_words("Seen my share of broken halos")
        self.assertEqual(karaoke_lyrics.word_error_rate(ref, ref), 0.0)
        self.assertAlmostEqual(karaoke_lyrics.word_error_rate(
            ref, karaoke_lyrics.lyric_words("St. Mysero, broken halo")), 5 / 6)
        self.assertEqual(karaoke_lyrics.word_error_rate([], []), 0.0)

    def test_drop_word_loops_removes_impossibly_fast_repeats(self):
        loop = LyricLine(14.14, " ".join(["la"] * 8), tuple((round(14.14 + 0.02 * i, 2), "la") for i in range(8)))
        sung = LyricLine(0.34, " ".join(["la"] * 8), tuple((round(0.34 + 0.3 * i, 2), "la") for i in range(8)))
        mixed = LyricLine(20.0, "x", ((20.0, "Oh"),) + tuple((20.5 + 0.01 * i, "na,") for i in range(7))
                          + ((21.0, "baby"),))
        out = karaoke_lyrics.drop_word_loops([loop, sung, mixed, LyricLine(30.0, "untimed")])
        self.assertEqual([ln.t for ln in out], [0.34, 20.0, 30.0])  # the loop line is gone
        self.assertEqual(out[1].text, "Oh baby")
        self.assertEqual(out[0], sung)

    def test_tighten_word_gaps_pulls_stray_early_words_forward(self):
        line = LyricLine(0.0, "Get a little closer", ((0.0, "Get"), (13.18, "a"), (17.46, "little"), (17.7, "closer")))
        held = LyricLine(30.0, "Ohhh baby", ((30.0, "Ohhh"), (35.5, "baby")))  # a held note after the first line
        parked = LyricLine(40.0, "after the break", ((40.0, "after"), (60.0, "the"), (60.4, "break")))
        fixed, kept, moved = karaoke_lyrics.tighten_word_gaps([line, held, parked])
        self.assertEqual(fixed.words, ((16.86, "Get"), (17.16, "a"), (17.46, "little"), (17.7, "closer")))
        self.assertEqual(fixed.t, 16.86)
        self.assertEqual(kept, held)  # 5.5s is a held note, not a stray word
        self.assertEqual(moved.words[0], (59.7, "after"))  # 20s isn't

    def test_render_ass_sweeps_word_by_word(self):
        line = LyricLine(10.0, "Seen my share", ((10.0, "Seen"), (10.7, "my"), (11.1, "share")))
        ass = karaoke_lyrics.render_ass([line, LyricLine(14.0, "")], duration_s=20, countdown=False)
        self.assertIn("{\\kf70}Seen {\\kf40}my {\\kf150}share", ass)  # last word fills for 1.5s
        late = karaoke_lyrics.render_ass([LyricLine(10.0, "x", ((10.5, "x"),))], duration_s=20, countdown=False)
        self.assertIn("{\\k50}{\\kf150}x", late)  # a pause before the first word

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

    def test_fetch_lrclib_retries_server_errors_only(self):
        class Resp:
            def __init__(self, code, data=None):
                self.status_code, self._data = code, data

            def json(self):
                return self._data

        replies = [Resp(503), Resp(503), Resp(200, {"id": 7, "plainLyrics": "hi", "syncedLyrics": None})]

        class Session:
            def get(self, url, params=None, headers=None, timeout=None):
                return replies.pop(0)

        with mock.patch.object(karaoke_lyrics.time, "sleep") as sleep:
            hit = karaoke_lyrics.fetch_lrclib("A", "B", session=Session(), retries=3)
        self.assertEqual(hit["id"], 7)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2.0, 4.0])
        replies[:] = [Resp(404), Resp(404)]  # not found is an answer: no retries
        with mock.patch.object(karaoke_lyrics.time, "sleep") as sleep:
            self.assertIsNone(karaoke_lyrics.fetch_lrclib("A", "B", session=Session(), retries=3))
        sleep.assert_not_called()

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

    def test_prep_video_is_noted_and_survives_a_refresh(self):
        out = os.path.join(self.tmp.name, "out")
        kwargs = dict(out_root=out, separator=self._fake_separator, online=False, log=lambda *_: None)
        meta = {"file_path": self.audio, "artist": "A", "title": "B"}
        fetched = []

        def fetch(song_dir, mix, *, source_path, artist, title, duration_s, log):
            fetched.append((mix, source_path, artist, title, duration_s))
            with open(os.path.join(song_dir, "video.mp4"), "wb") as fh:
                fh.write(b"mp4")
            return {"file": "video.mp4", "mode": "sync", "offset_s": 1.5, "confidence": 0.93}
        with mock.patch.object(self.prep, "analyze",
                               return_value={"bpm": 120.0, "first_beat_s": 0.0, "key": None, "duration_s": 80.0}):
            self.prep.prep_song(meta, **kwargs)
            with self.assertRaises(FileNotFoundError):  # not prepped: nothing to hang a video on
                self.prep.prep_video({"file_path": self.audio, "title": "Other"}, out_root=out, fetch=fetch)
            video = self.prep.prep_video(meta, out_root=out, fetch=fetch, log=lambda *_: None)
            self.assertEqual(fetched, [(self.audio, self.audio, "A", "B", 80.0)])
            self.assertEqual(self.prep.prep_song(meta, refresh=True, **kwargs)["video"], video)
        self.assertEqual(self.prep.prep_video(meta, out_root=out, fetch=fetch), video)  # kept, not re-fetched
        self.assertEqual(len(fetched), 1)
        self.assertEqual(self.prep.prep_video(meta, out_root=out, refresh=True, fetch=lambda *a, **k: None,
                                              log=lambda *_: None), video)  # nothing better: the old one stays
        self.assertTrue(self.prep.rebuild_index(out)[0]["has_video"])
        os.remove(os.path.join(out, "A - B", "video.mp4"))
        self.assertFalse(self.prep.rebuild_index(out)[0]["has_video"])

    def _fake_karaoke_gen(self, audio_path, song_dir, model):
        for name in ("backing.flac", "backing_bv.flac", "guide.flac"):
            open(os.path.join(song_dir, name), "wb").close()
        return {"lines": [LyricLine(10.0, "Seen my share", ((10.0, "Seen"), (10.7, "my"), (11.1, "share")))],
                "lyrics_source": "karaoke-gen", "model": "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
                "references": ["file"]}

    def test_karaoke_gen_lyrics_are_word_timed_and_survive_refresh(self):
        out = os.path.join(self.tmp.name, "out")
        bare = os.path.join(self.tmp.name, "src", "A - B.flac")  # no sidecar: no reference lyrics offline
        open(bare, "wb").close()
        meta = {"file_path": bare, "artist": "A", "title": "B"}
        quiet = dict(out_root=out, online=False, log=lambda *_: None)
        with mock.patch.object(self.prep, "analyze",
                               return_value={"bpm": 120.0, "first_beat_s": 0.0, "key": None, "duration_s": 80.0}):
            song = self.prep.prep_song(meta, separator=self._fake_karaoke_gen, backend="karaoke-gen", **quiet)
            self.assertEqual((song["lyrics_source"], song["separator"]), ("karaoke-gen", "karaoke-gen"))
            self.assertEqual(song["separation_model"], "model_bs_roformer_ep_317_sdr_12.9755.ckpt")
            self.assertIsNone(song["demucs_model"])
            self.assertIsNone(song["lyrics_wer"])  # nothing to check against
            with open(os.path.join(out, "A - B", "lyrics.lrc"), encoding="utf-8") as fh:
                self.assertIn("<00:10.70>my", fh.read())
            with open(os.path.join(out, "A - B", "lyrics.ass"), encoding="utf-8") as fh:
                self.assertIn("{\\kf40}my", fh.read())
            # The sidecar .lrc is still there, but a refresh keeps the word-timed lyrics.
            song = self.prep.prep_song(meta, refresh=True, **quiet)
            self.assertEqual((song["lyrics_source"], song["separator"]), ("karaoke-gen", "karaoke-gen"))
            self.assertEqual(song["lyrics_references"], ["file"])

            def relyric(audio_path, song_dir, model):
                self.assertTrue(os.path.isfile(os.path.join(song_dir, "backing.flac")))  # stems kept
                return {"lines": [LyricLine(9.0, "New words", ((9.0, "New"), (9.5, "words")))],
                        "lyrics_source": "karaoke-gen", "model": None, "references": ["genius", "lrclib"]}
            song = self.prep.prep_song(meta, relyric=True, separator=relyric, **quiet)
        self.assertEqual(song["separation_model"], "model_bs_roformer_ep_317_sdr_12.9755.ckpt")
        self.assertEqual(song["lyrics_references"], ["genius", "lrclib"])
        with open(os.path.join(out, "A - B", "lyrics.lrc"), encoding="utf-8") as fh:
            self.assertIn("<00:09.50>words", fh.read())
        entry = self.prep.rebuild_index(out)[0]
        self.assertTrue(entry["has_backing_vocals"])
        self.assertTrue(entry["lyrics_need_review"])  # never compared with reference lyrics

    def test_choose_lyrics_falls_back_to_synced_reference_when_transcription_strays(self):
        ref = karaoke_lyrics.parse_lrc("[00:13.85]Now that I've lost everything to you\n"
                                       "[00:18.21]You say you wanna start something new\n")
        good = [LyricLine(13.9, "Now that I've lost everything to you"),
                LyricLine(18.2, "you say you want to start something new")]
        loop = [LyricLine(0.3, "la la la la la la la"), LyricLine(18.2, "you say you wanna start something new")]
        lines, source, wer = self.prep.choose_lyrics(good, ref, None, "lrclib")
        self.assertEqual((lines, source), (good, "karaoke-gen"))
        self.assertAlmostEqual(wer, 2 / 14, places=3)  # "wanna" heard as "want to"
        lines, source, wer = self.prep.choose_lyrics(loop, ref, None, "lrclib")
        self.assertEqual((lines, source), (ref, "lrclib"))
        self.assertGreater(wer, self.prep.MAX_TRANSCRIPT_WER)
        # A skipped verse loses even when the overall word error rate looks fine.
        long_ref = karaoke_lyrics.parse_lrc("".join(f"[00:{10 + 4 * i:02d}.00]line {i} has five words\n"
                                                    for i in range(10)))
        skipped = [LyricLine(10.0 + 4 * i, f"line {i} has five words") for i in range(3, 10)]
        lines, source, wer = self.prep.choose_lyrics(skipped, long_ref, None, "lrclib")
        self.assertEqual((source, wer), ("lrclib", 0.3))
        lines, source, _ = self.prep.choose_lyrics(skipped, long_ref, None, "lrclib", max_wer=0.5)
        self.assertEqual(source, "lrclib")  # 15 words skipped in a row
        # Plain-text reference: no timing to fall back to, so the transcription stays.
        lines, source, _ = self.prep.choose_lyrics(loop, [], "Now that I've lost everything to you", "lrclib-plain")
        self.assertEqual((lines, source), (loop, "karaoke-gen"))
        self.assertEqual(self.prep.choose_lyrics(good, [], None, "none"), (good, "karaoke-gen", None))

    def test_separate_with_karaoke_gen_imports_its_outputs(self):
        song_dir = os.path.join(self.tmp.name, "A - B")
        os.makedirs(song_dir)
        model = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
        calls = {}

        def runner(cmd, cwd, env, **_kw):
            calls.update(cmd=cmd, env=env)
            track = os.path.join(cmd[cmd.index("--output_dir") + 1], "A - B")
            os.makedirs(os.path.join(track, "stems"))
            os.makedirs(os.path.join(track, "lyrics"))
            for rel in (f"A - B (Instrumental {model}).flac",
                        "A - B (Instrumental +BV mel_band_roformer_karaoke.ckpt).flac",
                        f"stems/A - B (Vocals {model}).flac", "stems/A - B (Vocals htdemucs_6s.yaml).flac"):
                with open(os.path.join(track, rel), "w") as fh:
                    fh.write(rel)
            with open(os.path.join(track, "lyrics", "A - B (Lyrics Corrections).json"), "w") as fh:
                json.dump({"reference_lyrics": {"lrclib": {}, "genius": {}}}, fh)
            with open(os.path.join(track, "lyrics", "A - B (Karaoke).lrc"), "w") as fh:
                fh.write("[re:MidiCo]\n[00:01.000]1:/Hello \n[00:01.500]1:world\n")
            return mock.Mock(returncode=0)

        with mock.patch.object(self.prep, "to_flac", side_effect=shutil.copyfile):
            result = self.prep.separate_with_karaoke_gen(self.audio, song_dir, artist="A", title="B",
                                                         runner=runner)
        self.assertEqual(calls["env"]["SKIP_CORRECTION"], "false")
        self.assertIn("--prep-only", calls["cmd"])
        self.assertEqual(calls["cmd"][-3:], [self.audio, "A", "B"])
        self.assertNotIn("--lyrics_file", calls["cmd"])  # online sources stay on
        with open(os.path.join(song_dir, "backing.flac")) as fh:
            self.assertIn(f"Instrumental {model}", fh.read())
        with open(os.path.join(song_dir, "guide.flac")) as fh:
            self.assertIn(f"Vocals {model}", fh.read())  # the clean model's vocals, not htdemucs'
        for name in ("backing_bv.flac", "lyrics_corrections.json", "karaoke-gen.log"):
            self.assertTrue(os.path.isfile(os.path.join(song_dir, name)), name)
        self.assertFalse(os.path.isdir(os.path.join(song_dir, "stems")))  # only with keep_stems
        self.assertFalse([n for n in os.listdir(song_dir) if n.startswith("_karaoke-gen-")])
        self.assertEqual(result["lyrics_source"], "karaoke-gen")
        self.assertEqual(result["model"], model)
        self.assertEqual(result["references"], ["genius", "lrclib"])
        self.assertEqual(result["lines"][0].words, ((1.0, "Hello"), (1.5, "world")))

    def test_separate_with_karaoke_gen_fails_without_an_instrumental(self):
        song_dir = os.path.join(self.tmp.name, "A - B")
        os.makedirs(song_dir)
        with self.assertRaisesRegex(RuntimeError, "no instrumental"):
            self.prep.separate_with_karaoke_gen(self.audio, song_dir, runner=lambda *a, **k: mock.Mock(returncode=1))

    def test_reference_lyrics_file_sources(self):
        # A hand-placed .lrc always goes in, as plain text.
        sidecar = (karaoke_lyrics.parse_lrc(SONG_LRC), "sidecar", None)
        with mock.patch.dict(os.environ, {"GENIUS_API_TOKEN": "x"}):
            with self.prep.reference_lyrics_file(sidecar) as path:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
        self.assertIn("We are the front line", text)
        self.assertNotIn("[", text)
        self.assertFalse(os.path.exists(path))
        lrclib = ([], "lrclib-plain", "line one\n\nline two\n")
        with mock.patch.dict(os.environ, {"GENIUS_API_TOKEN": ""}):
            # Without Genius, LRCLIB (already fetched) is karaoke-gen's only source: hand it over.
            with self.prep.reference_lyrics_file(lrclib) as path:
                with open(path, encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), "line one\nline two\n")
            with self.prep.reference_lyrics_file(([], "none", None)) as path:
                self.assertIsNone(path)
        with mock.patch.dict(os.environ, {"GENIUS_API_TOKEN": "x"}):
            # With Genius, karaoke-gen asks LRCLIB and Genius itself; a file would switch them off.
            with self.prep.reference_lyrics_file(lrclib) as path:
                self.assertIsNone(path)

    def test_vocal_presence_tells_a_held_note_from_a_silent_intro(self):
        import numpy as np
        import soundfile as sf
        rate = 8000
        t = np.arange(rate * 10) / rate
        vocal = np.where((t > 4) & (t < 8), 0.5, 0.001) * np.sin(2 * np.pi * 220 * t)  # sung 4-8 s, bleed elsewhere
        path = os.path.join(self.tmp.name, "guide.flac")
        sf.write(path, vocal.astype("float32"), rate)
        sung = self.prep.vocal_presence(path)
        self.assertLess(sung(0.5, 3.5), 0.1)
        self.assertGreater(sung(4.5, 7.5), 0.9)
        self.assertIsNone(self.prep.vocal_presence(os.path.join(self.tmp.name, "missing.flac")))
        parked = LyricLine(0.0, "Get it", ((0.0, "Get"), (4.3, "it")))  # Whisper's word in the intro
        held = LyricLine(4.2, "Ohhh baby", ((4.2, "Ohhh"), (7.9, "baby")))  # held for 3.7 s
        moved, kept = karaoke_lyrics.tighten_word_gaps([parked, held], sung=sung)
        self.assertEqual(moved.words[0], (4.0, "Get"))
        self.assertEqual(kept, held)

    def test_concurrent_reference_lookups_share_one_fetch(self):
        meta = {"file_path": os.path.join(self.tmp.name, "src", "y.flac"), "artist": "A", "title": "Raced"}
        found = ([], "lrclib-plain", "words\n")

        def slow(*args, **kwargs):
            time.sleep(0.1)  # LRCLIB backing off while the prefetch and a lane both ask
            return found
        results = []
        with mock.patch.object(karaoke_lyrics, "find_lyrics", side_effect=slow) as find:
            threads = [threading.Thread(target=lambda: results.append(self.prep.reference_lyrics(meta)))
                       for _ in range(3)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
        find.assert_called_once()
        self.assertEqual(results, [found] * 3)

    def test_reference_lyrics_looks_up_once_and_retries_misses_later(self):
        meta = {"file_path": os.path.join(self.tmp.name, "src", "x.flac"), "artist": "A", "title": "Once",
                "duration": 200000}
        found = ([], "lrclib-plain", "words\n")
        with mock.patch.object(karaoke_lyrics, "find_lyrics", return_value=found) as find:
            self.assertEqual(self.prep.reference_lyrics(meta), found)
            self.assertEqual(self.prep.reference_lyrics(meta), found)
        find.assert_called_once()
        self.assertEqual(find.call_args.args[4], 200.0)
        self.assertEqual(find.call_args.kwargs["retries"], 4)
        miss = dict(meta, title="Missing")
        with mock.patch.object(karaoke_lyrics, "find_lyrics", return_value=([], "none", None)) as find, \
                mock.patch.object(self.prep.time, "time", side_effect=[1000.0, 1700.0, 1700.0]):
            self.prep.reference_lyrics(miss)
            self.prep.reference_lyrics(miss)  # ten minutes later: ask again
        self.assertEqual(find.call_count, 2)

    def test_suggest_preset_and_dirname(self):
        self.assertEqual(self.prep.suggest_preset(["Synth Punk"], []), "genre/synth-punk-pogo")
        self.assertEqual(self.prep.suggest_preset(["Hardcore Punk"], []), "genre/riot-mode")
        self.assertEqual(self.prep.suggest_preset(["New Wave"], []), "genre/synth-punk-pogo")
        self.assertEqual(self.prep.suggest_preset(["Heavy Metal"]), "genre/karaoke-metal")
        self.assertIsNone(self.prep.suggest_preset([], []))
        self.assertEqual(self.prep.safe_dirname('AC/DC', 'What?: "x"'), "AC_DC - What__ _x_")


class RemoteLaneTests(unittest.TestCase):
    def setUp(self):
        import karaoke_prep
        self.prep = karaoke_prep
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audio = os.path.join(self.tmp.name, "Song & odd! ✓.MP3")
        open(self.audio, "wb").close()
        self.lyrics = os.path.join(self.tmp.name, "ref.txt")
        open(self.lyrics, "w", encoding="utf-8").close()
        self.work = os.path.join(self.tmp.name, "song", "work")
        os.makedirs(self.work)

    def _lane(self, run_exit=0):
        calls = []
        self.meta = None

        def run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == "ssh" and " run " in cmd[-1]:
                return mock.Mock(returncode=run_exit)
            if cmd[0] == "scp" and cmd[-1].endswith("/in/meta.json"):
                with open(cmd[-2], encoding="utf-8") as fh:
                    self.meta = json.load(fh)
            elif cmd[0] == "scp" and "-r" in cmd:
                os.makedirs(os.path.join(cmd[-1], "out", "A - B"))
            elif cmd[0] == "scp" and cmd[-2].endswith("karaoke-gen.log"):
                with open(cmd[-1], "w", encoding="utf-8") as fh:
                    fh.write("separated on cuda\n")
            return mock.Mock(returncode=0, stdout="", stderr="")

        return self.prep.RemoteLane("goblindriver", r"D:\Karaoke\lane.cmd", "D:\\Karaoke\\work\\", run=run), calls

    def test_run_uploads_runs_fetches_and_cleans_up(self):
        lane, calls = self._lane()
        log_path = os.path.join(self.tmp.name, "log")
        with open(log_path, "w", encoding="utf-8") as log_fh:
            rc = lane.run(self.audio, self.work, artist='Björk & "B"', title="Help! 100%", lyrics_file=self.lyrics,
                          log_fh=log_fh)
        self.assertEqual(rc, 0)
        job = calls[0][-1].split("\\")[-2]
        self.assertTrue(job.startswith("citadel-"))
        self.assertEqual(calls[0][-1], f'mkdir "D:\\Karaoke\\work\\{job}\\in"')
        self.assertEqual(calls[1][-1], f"goblindriver:D:/Karaoke/work/{job}/in/input.mp3")  # odd names stay home
        self.assertEqual(calls[2][-1], f"goblindriver:D:/Karaoke/work/{job}/in/lyrics.txt")
        self.assertEqual(self.meta, {"artist": 'Björk & "B"', "title": "Help! 100%"})  # exact, via meta.json
        run_cmd = calls[4][-1]
        self.assertTrue(run_cmd.startswith(f"D:\\Karaoke\\lane.cmd run {job} \"--prep-only\""))
        self.assertIn(f'"--lyrics_file" "D:\\Karaoke\\work\\{job}\\in\\lyrics.txt"', run_cmd)
        self.assertTrue(run_cmd.endswith(f'"D:\\Karaoke\\work\\{job}\\in\\input.mp3"'))  # no names on cmd.exe
        self.assertEqual(os.listdir(self.work), ["A - B"])  # the track folder, ready to import
        self.assertEqual(calls[-1][-1], f'rmdir /s /q "D:\\Karaoke\\work\\{job}"')
        with open(log_path, encoding="utf-8") as fh:
            self.assertIn("separated on cuda", fh.read())

    def test_yield_skips_the_fetch_and_raises_through_the_importer(self):
        lane, calls = self._lane(run_exit=self.prep.LANE_YIELDED)
        song_dir = os.path.dirname(self.work)
        with self.assertRaises(self.prep.LaneYielded):
            self.prep.separate_with_karaoke_gen(self.audio, song_dir, artist="A", title="B", lane=lane)
        self.assertFalse(any(c[0] == "scp" and "-r" in c for c in calls))
        self.assertTrue(calls[-1][-1].startswith("rmdir /s /q"))

    def _failing_lane(self, fail):
        calls = []

        def run(cmd, **kwargs):
            calls.append(cmd)
            failure = fail(cmd)
            if isinstance(failure, BaseException):
                raise failure
            return mock.Mock(returncode=failure if failure is not None else 0, stdout="", stderr="")
        return self.prep.RemoteLane("goblindriver", run=run), calls

    def test_transport_failures_requeue_and_stop_the_remote_job(self):
        cases = {
            "upload": lambda c: subprocess.CalledProcessError(1, c) if c[0] == "scp" else None,
            "timeout": lambda c: subprocess.TimeoutExpired(c, 3600) if " run " in c[-1] else None,
            "dropped": lambda c: self.prep.RemoteLane.SSH_FAILED if " run " in c[-1] else None,
        }
        for name, fail in cases.items():
            with self.subTest(name):
                lane, calls = self._failing_lane(fail)
                with self.assertRaises(self.prep.LaneUnavailable):
                    lane.run(self.audio, self.work, artist="A", title="B")
                stops = [c for c in calls if c[0] == "ssh" and c[-1].endswith(" stop")]
                self.assertTrue(calls[-1][-1].startswith("rmdir /s /q"))
                if name == "upload":  # nothing was started, so nothing to stop (it could be another job)
                    self.assertEqual(stops, [])
                else:
                    self.assertEqual(calls[-2], stops[0])  # stop, then remove

    def test_free_reports_the_lane_check(self):
        lane = self.prep.RemoteLane("g", run=lambda cmd, **kw: mock.Mock(returncode=1, stdout="busy: game\n",
                                                                           stderr=""))
        self.assertEqual(lane.free(), (False, "busy: game"))

        def unreachable(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 60)
        self.assertFalse(self.prep.RemoteLane("g", run=unreachable).free()[0])


class PrepBatchTests(unittest.TestCase):
    def setUp(self):
        import karaoke_prep
        self.prep = karaoke_prep
        self.tracks = [{"artist": "A", "title": f"Song {i}"} for i in range(3)]

    def _batch(self, lane, fake, **kwargs):
        ran = []

        def prep_song(meta, lane=None, log=None, **_kw):
            fake(meta, lane)
            ran.append((meta["title"], lane.name if lane else "local"))
        with mock.patch.object(self.prep, "prep_song", side_effect=prep_song):
            done, failed = self.prep.prep_batch(self.tracks, lane=lane, log=lambda *_: None, poll_s=0.01,
                                                **kwargs)
        return done, failed, ran

    def test_free_remote_lane_takes_a_short_queue(self):
        lane = mock.Mock(free=mock.Mock(return_value=(True, "free")))
        lane.name = "goblindriver"
        done, failed, ran = self._batch(lane, lambda meta, lane: None)
        self.assertEqual((done, failed), (3, 0))
        self.assertEqual({where for _, where in ran}, {"goblindriver"})

    def test_busy_remote_lane_leaves_songs_to_the_local_one(self):
        lane = mock.Mock(free=mock.Mock(return_value=(False, "busy: game")))
        lane.name = "goblindriver"
        done, _, ran = self._batch(lane, lambda meta, lane: None)
        self.assertEqual(done, 3)
        self.assertEqual({where for _, where in ran}, {"local"})

    def test_yielded_song_goes_back_to_the_queue(self):
        lane = mock.Mock(free=mock.Mock(side_effect=[(True, "free")] + [(False, "busy: game")] * 1000))
        lane.name = "goblindriver"

        def fake(meta, use_lane):
            if use_lane is not None:
                raise self.prep.LaneYielded("game started")
        done, failed, ran = self._batch(lane, fake)
        self.assertEqual((done, failed), (3, 0))
        self.assertEqual(sorted(title for title, where in ran if where == "local"), ["Song 0", "Song 1", "Song 2"])

    def test_failures_are_counted_not_fatal(self):
        def fake(meta, use_lane):
            if meta["title"] == "Song 1":
                raise RuntimeError("bad file")
        done, failed, _ = self._batch(None, fake)
        self.assertEqual((done, failed), (2, 1))

    def test_local_lane_waits_for_a_late_yield(self):
        self.tracks = self.tracks[:1]
        lane = mock.Mock(free=mock.Mock(side_effect=[(True, "free")] + [(False, "busy: game")] * 1000))
        lane.name = "goblindriver"

        def fake(meta, use_lane):
            if use_lane is not None:  # the only song, taken while the local lane had nothing queued
                time.sleep(0.05)
                raise self.prep.LaneYielded("game started")
        done, failed, ran = self._batch(lane, fake)
        self.assertEqual((done, failed), (1, 0))
        self.assertEqual(ran, [("Song 0", "local")])

    def test_unreachable_lane_hands_songs_to_the_local_one(self):
        lane = mock.Mock(free=mock.Mock(return_value=(True, "free")))
        lane.name = "goblindriver"

        def fake(meta, use_lane):
            if use_lane is not None:
                raise self.prep.LaneUnavailable("goblindriver unavailable: timed out")
        done, failed, ran = self._batch(lane, fake)
        self.assertEqual((done, failed), (3, 0))
        self.assertEqual({where for _, where in ran}, {"local"})

    def test_remote_only_gives_up_after_its_tries(self):
        lane = mock.Mock(free=mock.Mock(return_value=(True, "free")))
        lane.name = "goblindriver"
        tries = []

        def fake(meta, use_lane):
            tries.append(meta["title"])
            raise self.prep.LaneUnavailable("timed out")
        done, failed, _ = self._batch(lane, fake, local=False)
        self.assertEqual((done, failed), (0, 3))
        self.assertEqual(len(tries), 3 * self.prep.REMOTE_TRIES)

    def test_game_yields_dont_use_up_remote_tries(self):
        self.tracks = self.tracks[:1]
        lane = mock.Mock(free=mock.Mock(return_value=(True, "free")))
        lane.name = "goblindriver"
        yields = []

        def fake(meta, use_lane):
            if len(yields) < 3:
                yields.append(meta["title"])
                raise self.prep.LaneYielded("game started")
        done, failed, ran = self._batch(lane, fake, local=False)
        self.assertEqual((done, failed, len(yields)), (1, 0, 3))
        self.assertEqual(ran, [("Song 0", "goblindriver")])

    def test_the_same_file_twice_is_prepped_once(self):
        self.tracks = [{"file_path": "/m/a.flac", "title": "A"}, {"file_path": "/m/a.flac", "title": "A"},
                       {"file_path": "/m/b.flac", "title": "B"}]
        done, _, ran = self._batch(None, lambda meta, lane: None)
        self.assertEqual((done, sorted(t for t, _ in ran)), (2, ["A", "B"]))

    def test_videos_follow_prepped_songs_on_their_own_thread(self):
        lane = mock.Mock(free=mock.Mock(return_value=(True, "free")))
        lane.name = "goblindriver"
        fetched, reported = [], []

        def prep_video(meta, *, out_root=None, refresh=False, log=None):
            fetched.append((meta["title"], refresh, threading.current_thread().name))
            if meta["title"] == "Song 2":
                raise RuntimeError("yt-dlp missing")
            return {"file": "video.mp4"}

        def fake(meta, use_lane):
            if meta["title"] == "Song 1":
                raise RuntimeError("bad file")
        with mock.patch.object(self.prep, "prep_video", side_effect=prep_video):
            done, failed, _ = self._batch(lane, fake, revideo=True,
                                          on_video=lambda meta, video, error: reported.append(
                                              (meta["title"], bool(video), error is not None)))
        self.assertEqual((done, failed), (2, 1))  # a missing video doesn't fail the song
        self.assertEqual(sorted(fetched), [("Song 0", True, "videos"), ("Song 2", True, "videos")])
        self.assertEqual(sorted(reported), [("Song 0", True, False), ("Song 2", False, True)])

    def test_no_videos_unless_asked(self):
        with mock.patch.object(self.prep, "prep_video") as prep_video:
            self._batch(None, lambda meta, lane: None)
        prep_video.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec("scipy"), "needs scipy")
class VideoTests(unittest.TestCase):
    def setUp(self):
        import karaoke_video
        self.kv = karaoke_video
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    ENTRIES = [
        {"id": "lyr", "title": "Le Tigre - Deceptacon (Lyrics)", "channel": "Stereogram", "duration": 185},
        {"id": "cov", "title": "Deceptacon (cover)", "channel": "Some Band", "duration": 185},
        {"id": "other", "title": "Deceptacon", "channel": "Some Band", "duration": 185},
        {"id": "topic", "title": "Deceptacon", "channel": "Le Tigre - Topic", "duration": 185},
        {"id": "fake", "title": "Le Tigre ft. Adele - Deceptacon (Official 2026 Video)", "channel": "x",
         "duration": 270},
        {"id": "live", "title": "Le Tigre - Deceptacon (Live at Farm Aid)", "channel": "Le Tigre", "duration": 190},
        {"id": "label", "title": "Le Tigre - Deceptacon (Official Video)", "channel": "Mr. Lady", "duration": 186},
        {"id": "own", "title": "Deceptacon", "channel": "LeTigreWorld", "duration": 185},
        {"id": "fan", "title": "Le Tigre - Deceptacon Music Video (Official)", "channel": "FanFilms",
         "duration": 185},
    ]

    def test_rank_prefers_the_artist_and_drops_lyric_cover_and_audio_uploads(self):
        ranked = [e["id"] for e in self.kv.rank_candidates(self.ENTRIES, "Le Tigre", "Deceptacon", 184.6)]
        self.assertEqual(ranked[0], "own")  # the artist's own upload beats anyone's "official" tag
        self.assertEqual(set(ranked[1:3]), {"fan", "label"})
        self.assertNotIn("lyr", ranked)
        self.assertNotIn("cov", ranked)
        self.assertNotIn("other", ranked)   # another channel, no artist named: a cover
        self.assertNotIn("topic", ranked)   # auto-generated audio
        self.assertLess(ranked.index("label"), ranked.index("live"))
        self.assertEqual(self.kv.rank_candidates(self.ENTRIES, None, "Deceptacon"), [])

    def test_skip_words_in_the_song_title_are_allowed(self):
        entries = [{"id": "a", "title": "Bruce Springsteen - Cover Me (Official Video)",
                    "channel": "Bruce Springsteen", "duration": 207}]
        self.assertEqual(len(self.kv.rank_candidates(entries, "Bruce Springsteen", "Cover Me", 207)), 1)

    def test_clean_title(self):
        self.assertEqual(self.kv.clean_title("Wild World (Remastered 2020)"), "Wild World")
        self.assertEqual(self.kv.clean_title("Because the Night - 2010 Remaster"), "Because the Night")
        self.assertEqual(self.kv.clean_title("Fineshrine"), "Fineshrine")

    def _envelope(self, seconds, seed):
        import numpy as np
        rng = np.random.default_rng(seed)
        env = rng.exponential(size=int(seconds * self.kv.SR / self.kv.HOP)) ** 3
        return (env - env.mean()) / env.std()

    def test_align_locks_the_same_audio_with_its_offset(self):
        import numpy as np
        song = self._envelope(180, 1)
        pad = self._envelope(12, 2)  # a 12 s intro before the song starts in the video
        video = np.concatenate([pad, song + 0.3 * self._envelope(180, 3), self._envelope(5, 4)])
        mode, offset_s, confidence = self.kv.align(song, video)
        self.assertEqual(mode, "sync")
        self.assertAlmostEqual(offset_s, len(pad) * self.kv.HOP / self.kv.SR, places=2)
        self.assertGreater(confidence, 0.9)

    def test_align_plays_other_takes_re_edits_and_bar_loops_loose(self):
        import numpy as np
        song = self._envelope(180, 1)
        self.assertEqual(self.kv.align(song, self._envelope(200, 5))[:2], ("loose", None))
        bar = self._envelope(2, 6)  # one bar copied over and over: every bar-length lag fits equally
        loop = np.tile(bar, 90)
        self.assertEqual(self.kv.align(loop, np.concatenate([self._envelope(3, 7), loop]))[:2], ("loose", None))
        cut = int(30 * self.kv.SR / self.kv.HOP)  # a radio edit: 30 s gone from the middle
        half = len(song) // 2
        self.assertEqual(self.kv.align(song, np.concatenate([song[:half], song[half + cut:]]))[:2],
                         ("loose", None))

    def test_is_still_compares_keyframes(self):
        import numpy as np
        same = np.full((4, 576), 80, dtype=np.uint8).tobytes()
        moving = np.concatenate([np.full((2, 576), 80), np.full((2, 576), 200)]).astype(np.uint8).tobytes()
        for frames, expected in ((same, True), (moving, False), (b"", True)):
            with mock.patch.object(self.kv.subprocess, "run",
                                   return_value=subprocess.CompletedProcess([], 0, stdout=frames)):
                self.assertEqual(self.kv.is_still("v.mp4"), expected)

    def _fake_ytdlp(self, cmd, **_kw):
        if "--dump-single-json" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"entries": self.ENTRIES}), stderr="")
        dest = cmd[cmd.index("-o") + 1]
        with open(dest, "wb") as fh:
            fh.write(cmd[-1].encode())
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def test_fetch_video_skips_still_pictures_and_records_its_pick(self):
        song_dir = os.path.join(self.tmp.name, "Le Tigre - Deceptacon")
        os.makedirs(song_dir)
        open(os.path.join(song_dir, "video.webm"), "wb").close()  # an older fetch, replaced
        env = self._envelope(180, 1)
        still = lambda path: open(path, "rb").read().endswith(b"own")  # noqa: E731
        with mock.patch.object(self.kv, "video_duration", return_value=186.0):
            video = self.kv.fetch_video(song_dir, os.path.join(self.tmp.name, "Deceptacon.mp3"),
                                        artist="Le Tigre", title="Deceptacon", duration_s=184.6,
                                        log=lambda *_: None, run=self._fake_ytdlp, envelope=lambda p: env,
                                        still=still)
        self.assertEqual((video["file"], video["mode"], video["offset_s"]), ("video.mp4", "sync", 0.0))
        self.assertEqual((video["origin"], video["channel"], video["duration_s"]), ("yt-dlp", "Mr. Lady", 186.0))
        self.assertTrue(video["source"].endswith("v=label"))
        self.assertEqual(sorted(os.listdir(song_dir)), ["video.mp4"])  # temp folder gone, old video replaced

    def test_fetch_video_gives_up_quietly_when_nothing_fits(self):
        song_dir = os.path.join(self.tmp.name, "song")
        os.makedirs(song_dir)
        video = self.kv.fetch_video(song_dir, "x.mp3", artist="Nobody", title="Nothing", log=lambda *_: None,
                                    run=self._fake_ytdlp, envelope=lambda p: None, still=lambda p: False)
        self.assertIsNone(video)
        self.assertEqual(os.listdir(song_dir), [])

    def test_a_video_beside_the_source_wins(self):
        song_dir = os.path.join(self.tmp.name, "song")
        os.makedirs(song_dir)
        source = os.path.join(self.tmp.name, "Deceptacon.flac")
        open(source, "wb").close()
        with open(os.path.join(self.tmp.name, "Deceptacon.mkv"), "wb") as fh:
            fh.write(b"mkv")
        never = mock.Mock(side_effect=AssertionError("searched YouTube"))
        with mock.patch.object(self.kv, "video_duration", return_value=None):
            video = self.kv.fetch_video(song_dir, source, artist="Le Tigre", title="Deceptacon",
                                        log=lambda *_: None, run=never, envelope=lambda p: None)
        self.assertEqual((video["file"], video["origin"], video["mode"]), ("video.mkv", "local", "loose"))
        with open(os.path.join(song_dir, "video.mkv"), "rb") as fh:
            self.assertEqual(fh.read(), b"mkv")


class DeckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deck = _load_deck()

    def test_songs_never_share_the_gpu_lanes_folder(self):
        # D:\Karaoke holds the GPU lane (venv, models, work); a /MIR mirror into it would delete them.
        if os.name == "nt":
            self.assertEqual(self.deck.DEFAULT_ROOT, r"D:\Karaoke\Songs")
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(SystemExit) as ctx:
                self.deck.load_index(root)
        self.assertIn(r"D:\Karaoke\Songs /MIR", str(ctx.exception))

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

    def test_find_mpv_falls_back_to_wingets_install_folder(self):
        d = self.deck
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "MPV Player", "mpv.exe")
            os.makedirs(os.path.dirname(exe))
            open(exe, "wb").close()
            with mock.patch.object(d.shutil, "which", return_value=None), \
                 mock.patch.object(d.os, "name", "nt"), \
                 mock.patch.dict(d.os.environ, {"ProgramFiles": tmp, "LOCALAPPDATA": ""}):
                self.assertEqual(d.find_mpv(), exe)
                self.assertEqual(d.find_mpv(r"C:\custom\mpv.exe"), r"C:\custom\mpv.exe")
            with mock.patch.object(d.shutil, "which", return_value="/usr/bin/mpv"):
                self.assertEqual(d.find_mpv(), "/usr/bin/mpv")

    def test_mido_uses_pygame_without_rtmidi_unless_a_backend_is_set(self):
        fake_mido = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"mido": fake_mido, "rtmidi": None}), \
             mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MIDO_BACKEND", None)
            self.assertIs(self.deck.load_mido(), fake_mido)
            fake_mido.set_backend.assert_called_once_with("mido.backends.pygame")
            fake_mido.set_backend.reset_mock()
            os.environ["MIDO_BACKEND"] = "mido.backends.portmidi"
            self.deck.load_mido()
            fake_mido.set_backend.assert_not_called()

    def test_ipc_reader_joins_split_events_and_stops_at_end_file(self):
        mpv = object.__new__(self.deck.Mpv)
        mpv.state = {"time-pos": None, "pause": False, "speed": 1.0}
        mpv.state_at = 0.0
        mpv.closed = threading.Event()
        chunks = iter([b'{"event":"property-change","name":"time-pos","data":1.5}\n{"ev',
                       b'ent":"property-change","name":"pause","data":true}\n',
                       b'{"event":"end-file"}\n', b'{"event":"property-change","name":"time-pos","data":9}\n'])
        mpv._recv_raw = lambda: next(chunks, b"")
        mpv._reader()
        self.assertTrue(mpv.closed.is_set())
        self.assertEqual((mpv.state["time-pos"], mpv.state["pause"]), (1.5, True))

    @unittest.skipUnless(os.name == "nt", "Windows named pipes")
    def test_commands_reach_a_silent_mpv_on_windows(self):
        # A blocking read on a synchronous pipe handle used to hold up every
        # write until mpv sent something: while paused, never.
        import _winapi
        name = r"\\.\pipe\jambox-deck-test-%d" % os.getpid()
        pipe = _winapi.CreateNamedPipe(          # byte mode is 0, so PIPE_WAIT alone
            name, _winapi.PIPE_ACCESS_DUPLEX, _winapi.PIPE_WAIT, 1, 65536, 65536, 0, _winapi.NULL)
        received = []

        def silent_server():
            _winapi.ConnectNamedPipe(pipe, False)
            data = b""
            while data.count(b"\n") < 4:          # 3 observe_property + the pause command
                data += _winapi.ReadFile(pipe, 4096)[0]
            received.append(data)
            _winapi.WriteFile(pipe, b'{"event":"end-file"}\n')

        result = {}

        def client():
            mpv = self.deck.Mpv(name, timeout=5)
            mpv.command("set_property", "pause", False)
            result["closed"] = mpv.closed.wait(5)

        threading.Thread(target=silent_server, daemon=True).start()
        worker = threading.Thread(target=client, daemon=True)
        worker.start()
        worker.join(10)
        # Left open on failure: closing a handle with a blocked read would hang too.
        self.assertFalse(worker.is_alive(), "a command blocked behind the pending pipe read")
        _winapi.CloseHandle(pipe)
        self.assertTrue(result.get("closed"))
        self.assertIn(b'"pause", false', received[0])


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


class KaraokeApiTests(unittest.TestCase):
    def setUp(self):
        web_dir = os.path.join(REPO_ROOT, "web")
        if web_dir not in sys.path:
            sys.path.insert(0, web_dir)
        from flask import Flask
        from api.karaoke import karaoke_bp
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "Karaoke")
        song_dir = os.path.join(self.root, "Home Front - Test")
        os.makedirs(song_dir)
        for name in ("backing.flac", "guide.flac"):
            with open(os.path.join(song_dir, name), "wb") as fh:
                fh.write(b"fLaC")
        with open(os.path.join(song_dir, "lyrics.lrc"), "w") as fh:
            fh.write(SONG_LRC)
        with open(os.path.join(song_dir, "song.json"), "w") as fh:
            json.dump({"artist": "Home Front", "title": "Test", "bpm": 120.0, "beat_offset_s": 0.5,
                       "duration_s": 80.0, "energy": "high", "choruses": [[17.5, 25.5], [61.5, 69.5]],
                       "preset": "genre/synth-punk-pogo", "drops": [], "drops_locked": False,
                       "has_lyrics": True}, fh)
        app = Flask(__name__)
        app.config.update(KARAOKE_DIR=self.root, TESTING=True)
        app.register_blueprint(karaoke_bp, url_prefix="/api")
        self.client = app.test_client()
        self.dir = "Home Front - Test"

    def test_songs_and_detail(self):
        songs = self.client.get("/api/karaoke/songs").get_json()["songs"]
        self.assertEqual([s["dir"] for s in songs], [self.dir])
        self.assertTrue(songs[0]["has_guide"])
        detail = self.client.get(f"/api/karaoke/song/{self.dir}").get_json()
        self.assertEqual(detail["song"]["artist"], "Home Front")
        self.assertEqual(detail["lyrics"][0], {"t": 10.0, "text": "Verse line one"})
        self.assertTrue(detail["has_guide"])

    def test_status_reports_karaoke_gen_and_the_lane(self):
        import api.karaoke as karaoke_api
        with mock.patch.object(karaoke_api, "_get_plex", return_value=None):
            tools = self.client.get("/api/karaoke/status").get_json()["tools"]
        self.assertIsInstance(tools["karaoke_gen"], bool)
        self.assertIn(tools["backend"], ("karaoke-gen", "demucs"))
        self.assertIn("remote_lane", tools)

    def test_rejects_traversal_and_unknown(self):
        for bad in ("..", "_index.json", "nope"):
            self.assertEqual(self.client.get(f"/api/karaoke/song/{bad}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/karaoke/audio/{self.dir}/song.json").status_code, 404)

    def test_audio_served(self):
        resp = self.client.get(f"/api/karaoke/audio/{self.dir}/backing")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"fLaC")
        resp.close()

    def test_save_drops_locks_and_validates(self):
        resp = self.client.put(f"/api/karaoke/song/{self.dir}/drops",
                               json={"drops": [{"t": 12, "bank": "a", "pad": 3, "vel": 999, "label": "horn"}],
                                     "preset": "genre/riot-mode"})
        data = resp.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["drops"][0], {"t": 12.0, "bank": "A", "pad": 3, "vel": 127, "label": "horn"})
        with open(os.path.join(self.root, self.dir, "song.json")) as fh:
            saved = json.load(fh)
        self.assertTrue(saved["drops_locked"])
        self.assertEqual(saved["preset"], "genre/riot-mode")
        bad = self.client.put(f"/api/karaoke/song/{self.dir}/drops", json={"drops": [{"t": 1, "pad": 99}]})
        self.assertEqual(bad.status_code, 400)

    def test_redraft_unlocks(self):
        data = self.client.post(f"/api/karaoke/song/{self.dir}/redraft").get_json()
        self.assertFalse(data["drops_locked"])
        self.assertTrue(any(d["label"] == "air horn: chorus 1" for d in data["drops"]))

    def test_set_plan_prefers_song_presets(self):
        from api.karaoke import plan_karaoke_set
        plan = plan_karaoke_set(["genre/disco-inferno", "genre/disco-inferno", "genre/riot-mode", None,
                                 "genre/karaoke-metal"])
        self.assertEqual(plan[:5], [("a", "utility/karaoke-drops"), ("b", "genre/weapons-cache"),
                                    ("c", "genre/karaoke-metal"), ("d", "genre/disco-inferno"),
                                    ("e", "genre/riot-mode")])
        self.assertEqual(len(plan), 10)
        self.assertEqual(len({ref for _, ref in plan}), 10)
        import preset_utils
        for _, ref in plan:
            self.assertTrue(preset_utils.load_preset(ref), ref)

    def test_load_set_uses_preset_utils(self):
        import preset_utils
        with mock.patch.object(preset_utils, "load_preset_to_bank", return_value={"name": "x"}) as m:
            data = self.client.post("/api/karaoke/load-set").get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(m.call_count, 10)
        self.assertEqual(m.call_args_list[0].args, ("utility/karaoke-drops", "a"))

    def test_prep_requires_source(self):
        resp = self.client.post("/api/karaoke/prep", json={"dir": "nope"})
        self.assertEqual(resp.status_code, 404)
        resp = self.client.post("/api/karaoke/prep", json={"model": "bogus"})
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post("/api/karaoke/prep", json={"model": "karaoke-gen", "dir": "nope"})
        self.assertEqual(resp.status_code, 404)  # karaoke-gen passes validation

    def test_video_shows_in_the_list_and_detail(self):
        song_dir = os.path.join(self.root, self.dir)
        with open(os.path.join(song_dir, "song.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        data["video"] = {"file": "video.mp4", "mode": "loose", "offset_s": None}
        with open(os.path.join(song_dir, "song.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        self.assertFalse(self.client.get(f"/api/karaoke/song/{self.dir}").get_json()["has_video"])  # no file
        open(os.path.join(song_dir, "video.mp4"), "wb").close()
        self.assertTrue(self.client.get(f"/api/karaoke/song/{self.dir}").get_json()["has_video"])
        self.assertTrue(self.client.get("/api/karaoke/songs").get_json()["songs"][0]["has_video"])

    def test_revideo_on_a_song_only_fetches_its_video(self):
        import api.karaoke as karaoke_api
        with mock.patch.object(karaoke_api, "_run_prep") as run_prep:
            resp = self.client.post("/api/karaoke/prep", json={"dir": self.dir, "revideo": True})
            self.assertTrue(resp.get_json()["ok"])
            for _ in range(100):
                if run_prep.called:
                    break
                time.sleep(0.01)
        opts = run_prep.call_args.args[3]
        self.assertEqual((opts["videos"], opts["revideo"], opts["refresh"], opts["force"]),
                         (True, True, False, False))


class ChorusGapTests(unittest.TestCase):
    def test_instrumental_gap_splits_choruses(self):
        lines = karaoke_lyrics.parse_lrc(
            "[00:10.00]verse a\n[00:14.00]hook one\n[00:18.00]hook two\n[00:22.00]verse b\n"
            "[00:26.00]hook one\n[00:30.00]hook two\n[00:34.00]\n[00:50.00]hook one\n[00:54.00]hook two\n")
        self.assertEqual([c[0] for c in karaoke_lyrics.find_choruses(lines)], [14.0, 26.0, 50.0])

    def test_long_silence_splits_choruses(self):
        lines = karaoke_lyrics.parse_lrc(
            "[00:10.00]hook one\n[00:14.00]hook two\n[00:40.00]hook one\n[00:44.00]hook two\n[00:48.00]end\n")
        self.assertEqual([c[0] for c in karaoke_lyrics.find_choruses(lines)], [10.0, 40.0])
