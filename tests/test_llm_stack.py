"""LLM client routing, parsing, retries, and the smart-retag paths that use it."""
import _thread
import http.client
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import llm_client
import smart_retag
import vibe_generate
import vibe_training_store
from jambox_config import load_tag_db, upsert_tag_entries
from llm_client import LLMError, call_llm_chat, resolve_backend


OLLAMA = "http://127.0.0.1:11434/v1/chat/completions"
LLAMA_CPP = "http://127.0.0.1:8080/v1/chat/completions"


class BackendTests(unittest.TestCase):
    def test_only_ollamas_port_is_rerouted_in_auto_mode(self):
        self.assertEqual(resolve_backend(OLLAMA), ("http://127.0.0.1:11434/api/chat", True))
        self.assertEqual(resolve_backend(LLAMA_CPP), (LLAMA_CPP, False))
        self.assertEqual(resolve_backend("http://box:11434/api/chat"), ("http://box:11434/api/chat", True))

    def test_a_bare_base_url_gets_the_chat_path(self):
        self.assertEqual(resolve_backend("http://100.71.235.42:11434"), ("http://100.71.235.42:11434/api/chat", True))
        self.assertEqual(resolve_backend("http://box:11434/"), ("http://box:11434/api/chat", True))
        self.assertEqual(resolve_backend("http://box:8080"), ("http://box:8080/v1/chat/completions", False))
        self.assertEqual(resolve_backend("http://box:11434", "openai"), ("http://box:11434/v1/chat/completions", False))
        self.assertEqual(resolve_backend("http://box:8080", "ollama"), ("http://box:8080/api/chat", True))

    def test_explicit_backend_wins(self):
        self.assertEqual(resolve_backend(OLLAMA, "openai"), (OLLAMA, False))
        self.assertEqual(resolve_backend(LLAMA_CPP, "ollama"), ("http://127.0.0.1:8080/api/chat", True))

    def test_payload_shape_follows_the_backend(self):
        sent = {}

        def fake(url, payload, timeout):
            sent["url"], sent["payload"] = url, payload
            if url.endswith("/api/chat"):
                return {"message": {"content": '{"ok": 1}'}}
            return {"choices": [{"message": {"content": '{"ok": 1}'}}]}

        with patch.object(llm_client, "call_json_endpoint", side_effect=fake):
            self.assertEqual(call_llm_chat(OLLAMA, "m", [], num_ctx=8192), {"ok": 1})
            self.assertEqual(sent["payload"]["options"]["num_ctx"], 8192)
            self.assertFalse(sent["payload"]["think"])
            self.assertEqual(call_llm_chat(LLAMA_CPP, "m", []), {"ok": 1})
            self.assertEqual(sent["url"], LLAMA_CPP)
            self.assertIn("response_format", sent["payload"])


class ParseTests(unittest.TestCase):
    def test_only_dicts_come_back(self):
        parse = llm_client._repair_and_parse
        self.assertIsNone(parse('["kick", "snare"]'))
        self.assertIsNone(parse('"just a string"'))
        self.assertEqual(parse('[{"a": 1}]'), {"a": 1})

    def test_braces_inside_strings_and_prose_around_json(self):
        text = 'Sure! Here you go: {"sonic_description": "a } shaped thud", "quality_score": 4} hope that helps'
        self.assertEqual(llm_client._repair_and_parse(text),
                         {"sonic_description": "a } shaped thud", "quality_score": 4})

    def test_truncated_object_is_closed(self):
        self.assertEqual(llm_client._repair_and_parse('{"quality_score": 3'), {"quality_score": 3})

    def test_vibe_parser_treats_non_dict_as_failure(self):
        with patch.object(vibe_generate, "call_llm_chat", return_value=["funk"]), \
             patch.dict(vibe_generate.SETTINGS, {"LLM_ENDPOINT": OLLAMA}):
            with self.assertRaises(LLMError) as ctx:
                vibe_generate._call_llm("funky drums")
        self.assertEqual(ctx.exception.code, "empty_response")


PRIMARY = "http://100.71.235.42:11434"
FALLBACK = "http://100.67.11.60:11434"


class FallbackTests(unittest.TestCase):
    def setUp(self):
        llm_client._primary_down_until.clear()
        self.urls = []

    def _serve(self, down=(), code="connection_error"):
        def endpoint(url, _payload, timeout):
            self.urls.append(url)
            if any(url.startswith(d) for d in down):
                raise LLMError(code, "unreachable")
            return {"message": {"content": '{"ok": true}'}}
        return patch.object(llm_client, "call_json_endpoint", side_effect=endpoint)

    def test_an_unreachable_primary_falls_back_then_is_skipped_for_a_while(self):
        stats = []
        with self._serve(down=[PRIMARY]):
            self.assertEqual(call_llm_chat(PRIMARY, "m", [], fallback_endpoint=FALLBACK, on_stat=stats.append), {"ok": True})
            self.assertEqual(call_llm_chat(PRIMARY, "m", [], fallback_endpoint=FALLBACK), {"ok": True})
        self.assertEqual(self.urls, [PRIMARY + "/api/chat", FALLBACK + "/api/chat", FALLBACK + "/api/chat"])
        self.assertIn("fallback", stats)

    def test_the_primary_is_tried_again_after_the_retry_window(self):
        with self._serve(down=[PRIMARY]):
            call_llm_chat(PRIMARY, "m", [], fallback_endpoint=FALLBACK)
        llm_client._primary_down_until[PRIMARY] = 0
        self.urls.clear()
        with self._serve():
            call_llm_chat(PRIMARY, "m", [], fallback_endpoint=FALLBACK)
        self.assertEqual(self.urls, [PRIMARY + "/api/chat"])

    def test_a_timeout_falls_back_but_an_http_error_does_not(self):
        with self._serve(down=[PRIMARY], code="timeout"):
            self.assertEqual(call_llm_chat(PRIMARY, "m", [], fallback_endpoint=FALLBACK), {"ok": True})
        llm_client._primary_down_until.clear()
        with self._serve(down=[PRIMARY], code="http_error"):
            with self.assertRaises(LLMError):
                call_llm_chat(PRIMARY, "m", [], fallback_endpoint=FALLBACK)

    def test_without_a_fallback_the_error_surfaces(self):
        with self._serve(down=[PRIMARY]):
            with self.assertRaises(LLMError):
                call_llm_chat(PRIMARY, "m", [])

    def test_vibe_fallback_only_backs_up_the_base_model(self):
        settings = {"LLM_ENDPOINT": PRIMARY, "LLM_MODEL": "qwen3.5:9b", "LLM_FALLBACK_ENDPOINT": FALLBACK,
                    "VIBE_PARSER_MODE": "fine_tuned", "FINE_TUNED_LLM_ENDPOINT": "http://127.0.0.1:8080",
                    "FINE_TUNED_LLM_MODEL": "jambox-lora"}
        with patch.dict(vibe_generate.SETTINGS, settings):
            self.assertEqual(vibe_generate._parser_runtime()["fallback_endpoint"], "")
            vibe_generate.SETTINGS["VIBE_PARSER_MODE"] = "rag"
            self.assertEqual(vibe_generate._parser_runtime()["fallback_endpoint"], FALLBACK)


class RetryTests(unittest.TestCase):
    def _attempts(self, error, retries=3):
        calls = []

        def fail(*_args, **_kwargs):
            calls.append(1)
            raise error

        with patch.object(llm_client, "call_json_endpoint", side_effect=fail), \
             patch.object(llm_client.time, "sleep") as sleep:
            with self.assertRaises(LLMError):
                call_llm_chat(OLLAMA, "m", [], retries=retries)
        return len(calls), sleep.call_count

    def test_server_down_fails_fast(self):
        self.assertEqual(self._attempts(LLMError("connection_error", "refused")), (1, 0))

    def test_a_server_dying_mid_request_is_a_connection_error(self):
        # Seen when llama-server stopped under a live retag: resets and
        # RemoteDisconnected escaped as raw exceptions and skipped the stats.
        for raw in (ConnectionResetError(54, "Connection reset by peer"),
                    http.client.RemoteDisconnected("Remote end closed connection without response")):
            with patch.object(llm_client.urllib.request, "urlopen", side_effect=raw):
                with self.assertRaises(LLMError) as caught:
                    llm_client.call_json_endpoint(OLLAMA, {}, timeout=1)
            self.assertEqual(caught.exception.code, "connection_error")
            self.assertFalse(caught.exception.retryable)

    def test_an_unreachable_host_fails_fast(self):
        # A connect that times out (box asleep, Tailscale peer offline) comes back
        # wrapped in URLError; it used to be retried 4x at the OS connect timeout.
        with patch.object(llm_client.urllib.request, "urlopen",
                          side_effect=urllib.error.URLError(TimeoutError("timed out"))):
            with self.assertRaises(LLMError) as caught:
                llm_client.call_json_endpoint(OLLAMA, {}, timeout=1)
        self.assertEqual(caught.exception.code, "connection_error")
        with patch.object(llm_client.urllib.request, "urlopen", side_effect=TimeoutError("slow reply")):
            with self.assertRaises(LLMError) as caught:
                llm_client.call_json_endpoint(OLLAMA, {}, timeout=1)
        self.assertTrue(caught.exception.retryable)

    def test_client_errors_are_not_retried(self):
        self.assertEqual(self._attempts(LLMError("http_error", "404", status=404)), (1, 0))

    def test_timeouts_and_server_errors_are_retried(self):
        self.assertEqual(self._attempts(LLMError("timeout", "slow"))[0], 4)
        self.assertEqual(self._attempts(LLMError("http_error", "503", status=503))[0], 4)


class SmartRetagTests(unittest.TestCase):
    def test_no_repair_pass_when_the_server_is_unreachable(self):
        calls = []

        def down(*_args, **_kwargs):
            calls.append(1)
            raise LLMError("connection_error", "refused")

        with patch.object(smart_retag, "LLM_ENDPOINT", OLLAMA), \
             patch.object(smart_retag, "call_llm_chat", side_effect=down), \
             patch.object(smart_retag, "_build_prompt", return_value="prompt"), \
             patch("sys.stderr"):
            tags, _model, skipped = smart_retag._llm_tag_with_repair("x.wav", {"duration": 1.0}, verbose=False)

        self.assertEqual((tags, skipped, len(calls)), ({}, False, 1))

    def test_ingest_backs_off_after_the_llm_fails(self):
        calls = []

        def down(*_args, **_kwargs):
            calls.append(1)
            smart_retag._bump_llm_stat("connection_error")
            raise LLMError("connection_error", "refused")

        with patch.object(smart_retag, "LLM_ENDPOINT", OLLAMA), \
             patch.object(smart_retag, "_llm_unavailable_until", 0.0), \
             patch.object(smart_retag, "librosa_available", return_value=True), \
             patch.object(smart_retag, "extract_features", return_value={"duration": 1.0}), \
             patch.object(smart_retag, "_build_prompt", return_value="prompt"), \
             patch.object(smart_retag, "call_llm_chat", side_effect=down), \
             patch("sys.stderr"), patch("builtins.print"):
            first = smart_retag.retag_single("a.wav", "a.wav", {"type_code": "KIK"})
            second = smart_retag.retag_single("b.wav", "b.wav", {"type_code": "SNR"})

        self.assertEqual(len(calls), 1)
        self.assertTrue(first["smart_retag_pending"])
        self.assertTrue(second["smart_retag_pending"])

    def test_ctrl_c_stops_a_batch_after_the_in_flight_files(self):
        started = []

        def slow(rel, *_args):
            started.append(rel)
            time.sleep(0.3)
            return {"rel_path": rel, "status": "error", "reason": "no_features"}

        files = [("f%02d.wav" % i, "f%02d.wav" % i) for i in range(30)]
        progress = {"processed": 0}
        timer = threading.Timer(0.5, _thread.interrupt_main)
        t0 = time.time()
        with patch.object(smart_retag, "_process_single_file", side_effect=slow), \
             patch.object(smart_retag, "_save_slim_checkpoint"), \
             patch("sys.stderr"):
            timer.start()
            with self.assertRaises(KeyboardInterrupt):
                smart_retag.retag_batch(files, {}, verbose=False, workers=2,
                                        progress=progress, checkpoint_meta={"t0": t0})
        timer.cancel()

        # Unfixed, the pool drained all 30 files (~4.5 s) before the interrupt surfaced.
        self.assertLess(time.time() - t0, 2.5)
        self.assertLess(len(started), 10)
        # Every file that started was handled, including the ones in flight at Ctrl-C.
        self.assertEqual(progress["processed"], len(started))

    def test_requeue_rule_counts_sonic_description_and_quality_only(self):
        done = {"tag_source": "smart_retag_v1", "sonic_description": "deep thud", "quality_score": 4}
        self.assertFalse(smart_retag._entry_needs_smart_retag(done))
        self.assertFalse(smart_retag._entry_needs_smart_retag({**done, "type_code": "DRM"}))
        self.assertFalse(smart_retag._entry_needs_smart_retag({**done, "tag_source": "smart_retag_v2_revibe"}))
        self.assertTrue(smart_retag._entry_needs_smart_retag({**done, "smart_retag_pending": True}))
        self.assertTrue(smart_retag._entry_needs_smart_retag({**done, "quality_score": None}))
        self.assertTrue(smart_retag._entry_needs_smart_retag({"sonic_description": "x", "quality_score": 3}))


def _reply(score):
    return {"sonic_description": "dry rim click q%d" % score, "quality_score": score, "type_code": "RIM"}


def _scripted_llm(scores_by_name):
    """Fake _llm_tag_with_repair: each file name gets its scores in order."""
    def fake(full_path, features, verbose=True, **_kw):
        score = scores_by_name[os.path.basename(full_path)].pop(0)
        return (_reply(score) if score else {}), "qwen3.5:9b", False
    return fake


class QuarantineVoteTests(unittest.TestCase):
    FEATURES = {"duration": 0.3, "spectral_centroid": 2100.0}

    def _process(self, scores):
        with patch.object(smart_retag, "LLM_ENDPOINT", OLLAMA), \
             patch.object(smart_retag, "extract_features", return_value=dict(self.FEATURES)), \
             patch.object(smart_retag, "_llm_tag_with_repair", side_effect=_scripted_llm({"rim.wav": scores})):
            return smart_retag._process_single_file(
                "Drums/Percussion/rim.wav", "rim.wav", {}, dry_run=False, verbose=False,
                delete_low_quality=False)

    def test_a_low_score_needs_a_second_low_vote_to_quarantine(self):
        confirmed = self._process([2, 1])
        self.assertEqual(confirmed["status"], "low_quality")
        self.assertEqual(confirmed["entry"]["quality_votes"], [2, 1])

        overturned = self._process([2, 4])
        self.assertEqual(overturned["status"], "tagged")
        self.assertEqual((overturned["qs"], overturned["entry"]["quality_score"]), (4, 4))
        self.assertEqual(overturned["entry"]["sonic_description"], "dry rim click q4")
        self.assertEqual(overturned["entry"]["quality_votes"], [2, 4])

        # No second vote (server dropped mid-run): stays put but queued for the next run.
        unanswered = self._process([2, 0])
        self.assertEqual(unanswered["status"], "incomplete")
        self.assertEqual(unanswered["entry"]["quality_votes"], [2])
        self.assertTrue(smart_retag._entry_needs_smart_retag(unanswered["entry"]))

    def test_passing_scores_take_one_call(self):
        result = self._process([3])
        self.assertEqual(result["status"], "tagged")
        self.assertNotIn("quality_votes", result["entry"])


class QuarantineRecheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = self.tmp.name
        self.tags = os.path.join(self.lib, "_tags.json")
        rows = {}
        for name, extra in (("restore.wav", {}), ("stays.wav", {}), ("split.wav", {}),
                            ("settled.wav", {"quality_votes": [2, 1]})):
            q_rel = "_QUARANTINE/Drums/Percussion/" + name
            os.makedirs(os.path.dirname(os.path.join(self.lib, q_rel)), exist_ok=True)
            with open(os.path.join(self.lib, q_rel), "wb") as fh:
                fh.write(b"RIFF")
            rows[q_rel] = {"type_code": "RIM", "tag_source": "smart_retag_v1", "quality_score": 2,
                           "sonic_description": "thin click", "path": q_rel,
                           "features": {"spectral_centroid": 2100.0}, "duration": 0.3, **extra}
        upsert_tag_entries(self.tags, rows)
        self.scores = {"restore.wav": [4, 4], "stays.wav": [1], "split.wav": [3, 2], "settled.wav": []}

    def tearDown(self):
        self.tmp.cleanup()

    def _recheck(self, apply):
        args = SimpleNamespace(apply=apply, workers=2, limit=None, type=None, quiet=True)
        with patch.object(smart_retag, "LIBRARY", self.lib), \
             patch.object(smart_retag, "TAGS_FILE", self.tags), \
             patch.object(smart_retag, "LLM_ENDPOINT", OLLAMA), \
             patch.object(smart_retag, "_llm_tag_with_repair", side_effect=_scripted_llm(self.scores)), \
             patch("builtins.print"):
            smart_retag.run_recheck_quarantine(args)
        return load_tag_db(self.tags)

    def test_majority_vote_restores_the_file_and_rekeys_its_row(self):
        db = self._recheck(apply=True)

        self.assertTrue(os.path.exists(os.path.join(self.lib, "Drums/Percussion/restore.wav")))
        self.assertFalse(os.path.exists(os.path.join(self.lib, "_QUARANTINE/Drums/Percussion/restore.wav")))
        self.assertNotIn("_QUARANTINE/Drums/Percussion/restore.wav", db)
        row = db["Drums/Percussion/restore.wav"]
        self.assertEqual((row["quality_score"], row["quality_votes"]), (4, [2, 4, 4]))
        self.assertEqual((row["path"], row["sonic_description"]), ("Drums/Percussion/restore.wav", "dry rim click q4"))

        self.assertEqual(db["_QUARANTINE/Drums/Percussion/stays.wav"]["quality_votes"], [2, 1])
        self.assertEqual(db["_QUARANTINE/Drums/Percussion/split.wav"]["quality_votes"], [2, 3, 2])
        self.assertEqual(db["_QUARANTINE/Drums/Percussion/settled.wav"]["quality_votes"], [2, 1])
        self.assertEqual(self.scores, {"restore.wav": [], "stays.wav": [], "split.wav": [], "settled.wav": []})

    def test_dry_run_moves_and_writes_nothing(self):
        before = load_tag_db(self.tags)
        db = self._recheck(apply=False)

        self.assertEqual(db, before)
        self.assertTrue(os.path.exists(os.path.join(self.lib, "_QUARANTINE/Drums/Percussion/restore.wav")))
        self.assertFalse(os.path.exists(os.path.join(self.lib, "Drums/Percussion/restore.wav")))

    def test_type_filter_ignores_case(self):
        with patch.object(smart_retag, "LIBRARY", self.lib):
            found = list(smart_retag._recheck_candidates(load_tag_db(self.tags), type_code="rim"))
        self.assertEqual(len(found), 3)   # settled.wav already has two low votes


class FileAndRowStayTogetherTests(unittest.TestCase):
    """A file and its tag row move together or not at all (review of PR #3)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = self.tmp.name
        self.tags = os.path.join(self.lib, "_tags.json")
        self.patches = [patch.object(smart_retag, "LIBRARY", self.lib),
                        patch.object(smart_retag, "TAGS_FILE", self.tags),
                        patch.object(smart_retag, "LLM_ENDPOINT", OLLAMA),
                        patch("sys.stderr"), patch("builtins.print")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _file(self, rel, row):
        os.makedirs(os.path.dirname(os.path.join(self.lib, rel)), exist_ok=True)
        with open(os.path.join(self.lib, rel), "wb") as fh:
            fh.write(b"RIFF")
        upsert_tag_entries(self.tags, {rel: {"features": {"spectral_centroid": 2100.0}, "duration": 0.3, **row}})

    def _retag(self, rel, scores):
        with patch.object(smart_retag, "_llm_tag_with_repair",
                          side_effect=_scripted_llm({os.path.basename(rel): scores})):
            smart_retag.retag_batch([(rel, os.path.join(self.lib, rel))], load_tag_db(self.tags),
                                    verbose=False, workers=1)
        return load_tag_db(self.tags)

    def test_a_successful_retag_clears_the_pending_flag(self):
        self._file("Drums/Kicks/kick.wav", {"type_code": "KIK", "smart_retag_pending": True})
        row = self._retag("Drums/Kicks/kick.wav", [4])["Drums/Kicks/kick.wav"]
        self.assertNotIn("smart_retag_pending", row)
        self.assertFalse(smart_retag._entry_needs_smart_retag(row))

    def test_quarantine_keeps_file_and_row_together_when_the_db_write_fails(self):
        rel, q_rel = "Drums/Percussion/rim.wav", "_QUARANTINE/Drums/Percussion/rim.wav"
        self._file(rel, {"type_code": "RIM"})
        with patch.object(smart_retag, "write_tag_changes",
                          side_effect=sqlite3.OperationalError("database is locked")):
            db = self._retag(rel, [2, 1])
        self.assertTrue(os.path.exists(os.path.join(self.lib, rel)))
        self.assertFalse(os.path.exists(os.path.join(self.lib, q_rel)))
        self.assertEqual(set(db), {rel})

        db = self._retag(rel, [2, 1])          # and normally it moves both
        self.assertEqual(set(db), {q_rel})
        self.assertTrue(os.path.exists(os.path.join(self.lib, q_rel)))
        self.assertEqual(db[q_rel]["quality_votes"], [2, 1])

    def test_a_user_set_quality_survives_a_low_model_score(self):
        rel = "SFX/Stabs-Hits/Seinfeld_George_Answering_Machine.mp3"
        self._file(rel, {"type_code": "VOX", "quality_score": 3, "quality_source": "user", "quality_votes": [1, 1]})
        scores = {os.path.basename(rel): [1]}
        with patch.object(smart_retag, "_llm_tag_with_repair", side_effect=_scripted_llm(scores)):
            smart_retag.retag_batch([(rel, os.path.join(self.lib, rel))], load_tag_db(self.tags),
                                    verbose=False, workers=1)
        db = load_tag_db(self.tags)

        self.assertEqual(set(db), {rel})                      # not quarantined
        self.assertTrue(os.path.exists(os.path.join(self.lib, rel)))
        row = db[rel]
        self.assertEqual((row["quality_score"], row["quality_source"]), (3, "user"))
        self.assertEqual(row["model_quality_score"], 1)       # the model's verdict, kept beside it
        self.assertEqual(scores[os.path.basename(rel)], [])   # one call: no second vote was asked

    def test_tagging_is_greedy_and_the_quarantine_vote_is_sampled(self):
        rel = "Drums/Percussion/rim.wav"
        self._file(rel, {"type_code": "RIM"})
        replies, temperatures = [_reply(2), _reply(4)], []

        def fake_chat(*_args, temperature, **_kwargs):
            temperatures.append(temperature)
            return replies.pop(0)

        with patch.object(smart_retag, "call_llm_chat", side_effect=fake_chat):
            smart_retag.retag_batch([(rel, os.path.join(self.lib, rel))], load_tag_db(self.tags),
                                    verbose=False, workers=1)

        self.assertEqual(temperatures, [smart_retag.TAG_TEMPERATURE, smart_retag.VOTE_TEMPERATURE])
        self.assertEqual(temperatures, [0.0, 0.3])
        self.assertEqual(load_tag_db(self.tags)[rel]["quality_score"], 4)  # the passing vote wins, as before

    def test_merge_keeps_a_user_set_quality_and_only_that(self):
        existing = {"quality_score": 4, "quality_source": "user"}
        entry = smart_retag._merge_tags(existing, _reply(2), None, "Drums/Kicks/k.wav")
        self.assertEqual((entry["quality_score"], entry["model_quality_score"]), (4, 2))
        model_only = smart_retag._merge_tags({"quality_score": 4}, _reply(2), None, "Drums/Kicks/k.wav")
        self.assertEqual(model_only["quality_score"], 2)

    def _quarantined(self):
        q_rel = "_QUARANTINE/Drums/Percussion/rim.wav"
        self._file(q_rel, {"type_code": "RIM", "tag_source": "smart_retag_v1", "quality_score": 2,
                           "sonic_description": "thin click", "path": q_rel})
        return q_rel, "Drums/Percussion/rim.wav", load_tag_db(self.tags)[q_rel]

    def test_ctrl_c_during_a_restore_leaves_file_and_row_together(self):
        q_rel, rel, entry = self._quarantined()
        real_write = smart_retag.write_tag_changes

        # Before the commit (e.g. waiting on a busy DB): both stay in quarantine.
        with patch.object(smart_retag, "write_tag_changes", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                smart_retag._restore_from_quarantine(q_rel, rel, entry, [2, 4, 4], _reply(4))
        self.assertTrue(os.path.exists(os.path.join(self.lib, q_rel)))
        self.assertEqual(set(load_tag_db(self.tags)), {q_rel})

        # Right after the commit: both stay restored.
        def write_then_interrupt(*args, **kwargs):
            real_write(*args, **kwargs)
            raise KeyboardInterrupt

        with patch.object(smart_retag, "write_tag_changes", side_effect=write_then_interrupt):
            with self.assertRaises(KeyboardInterrupt):
                smart_retag._restore_from_quarantine(q_rel, rel, entry, [2, 4, 4], _reply(4))
        self.assertTrue(os.path.exists(os.path.join(self.lib, rel)))
        self.assertEqual(set(load_tag_db(self.tags)), {rel})

    def test_restore_never_overwrites_a_slot_filled_since_the_scan(self):
        q_rel, rel, entry = self._quarantined()
        os.makedirs(os.path.dirname(os.path.join(self.lib, rel)), exist_ok=True)
        with open(os.path.join(self.lib, rel), "wb") as fh:
            fh.write(b"NEWER")
        with self.assertRaises(FileExistsError):
            smart_retag._restore_from_quarantine(q_rel, rel, entry, [2, 4, 4], _reply(4))
        with open(os.path.join(self.lib, rel), "rb") as fh:
            self.assertEqual(fh.read(), b"NEWER")
        self.assertTrue(os.path.exists(os.path.join(self.lib, q_rel)))


class ModelLabelTests(unittest.TestCase):
    def test_session_label_uses_the_configured_model(self):
        self.assertEqual(vibe_training_store._normalize_label({"LLM_MODEL": "qwen3.5:9b"}), "qwen3.5:9b")
        self.assertEqual(
            vibe_training_store._normalize_label({"VIBE_PARSER_MODE": "fine_tuned", "LLM_MODEL": "a",
                                                  "FINE_TUNED_LLM_MODEL": "tuned"}),
            "tuned",
        )


if __name__ == "__main__":
    unittest.main()
