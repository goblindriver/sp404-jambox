"""LLM client routing, parsing, retries, and the smart-retag paths that use it."""
import os
import sys
import tempfile
import unittest
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

        unanswered = self._process([2, 0])
        self.assertEqual(unanswered["status"], "tagged")
        self.assertEqual(unanswered["entry"]["quality_votes"], [2])

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
