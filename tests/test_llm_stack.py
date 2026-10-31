"""LLM client routing, parsing, retries, and the smart-retag paths that use it."""
import os
import sys
import unittest
from unittest.mock import patch


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import llm_client
import smart_retag
import vibe_generate
import vibe_training_store
from llm_client import LLMError, call_llm_chat, resolve_backend


OLLAMA = "http://127.0.0.1:11434/v1/chat/completions"
LLAMA_CPP = "http://127.0.0.1:8080/v1/chat/completions"


class BackendTests(unittest.TestCase):
    def test_only_ollamas_port_is_rerouted_in_auto_mode(self):
        self.assertEqual(resolve_backend(OLLAMA), ("http://127.0.0.1:11434/api/chat", True))
        self.assertEqual(resolve_backend(LLAMA_CPP), (LLAMA_CPP, False))
        self.assertEqual(resolve_backend("http://box:11434/api/chat"), ("http://box:11434/api/chat", True))

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
