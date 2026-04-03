import json
import os
import sys
import tempfile
import unittest
import importlib.util
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
WEB_DIR = os.path.join(REPO_ROOT, "web")
TRAINING_VIBE_DIR = os.path.join(REPO_ROOT, "training", "vibe")

for path in (SCRIPTS_DIR, WEB_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.vibe import vibe_bp
import vibe_generate
import vibe_retrieval
import vibe_training_store

eval_spec = importlib.util.spec_from_file_location("vibe_eval_model", os.path.join(TRAINING_VIBE_DIR, "eval_model.py"))
vibe_eval_model = importlib.util.module_from_spec(eval_spec)
eval_spec.loader.exec_module(vibe_eval_model)

prepare_spec = importlib.util.spec_from_file_location("vibe_prepare_dataset", os.path.join(TRAINING_VIBE_DIR, "prepare_dataset.py"))
vibe_prepare_dataset = importlib.util.module_from_spec(prepare_spec)
prepare_spec.loader.exec_module(vibe_prepare_dataset)

train_spec = importlib.util.spec_from_file_location("vibe_train_lora", os.path.join(TRAINING_VIBE_DIR, "train_lora.py"))
vibe_train_lora = importlib.util.module_from_spec(train_spec)
train_spec.loader.exec_module(vibe_train_lora)


class VibeTrainingStoreTests(unittest.TestCase):
    def test_create_update_and_complete_session(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = os.path.join(tempdir, "vibe.sqlite")
            session_id = vibe_training_store.create_session(
                {"prompt": "dusty funk", "bank": "b", "bpm": 110, "key": "Am"},
                {"parsed": {"keywords": ["dusty"]}, "draft_preset": {"pads": {1: "KIK dusty one-shot"}}},
                {"VIBE_PARSER_MODE": "base", "LLM_MODEL": "qwen"},
                db_path=db_path,
            )
            vibe_training_store.update_review(
                session_id,
                {"pads": {1: "KIK dusty one-shot"}},
                {"keywords": ["dusty"]},
                True,
                "b",
                db_path=db_path,
            )
            vibe_training_store.complete_apply(
                session_id,
                {"pads": {1: "KIK dusty one-shot"}},
                "auto/test",
                {"fetched": "1/12"},
                "Bank populated!",
                db_path=db_path,
            )

            rows = vibe_training_store.list_sessions(limit=5, db_path=db_path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session_status"], "applied")
        self.assertEqual(rows[0]["preset_ref"], "auto/test")


class VibeRetrievalTests(unittest.TestCase):
    def test_retrieve_session_examples_prefers_matching_prompts(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = os.path.join(tempdir, "vibe.sqlite")
            session_id = vibe_training_store.create_session(
                {"prompt": "dusty funk drums"},
                {"parsed": {"keywords": ["dusty", "funk"]}, "draft_preset": {"pads": {1: "KIK dusty one-shot"}}},
                {"VIBE_PARSER_MODE": "base", "LLM_MODEL": "qwen"},
                db_path=db_path,
            )
            vibe_training_store.promote_dataset_status(session_id, "reviewed", db_path=db_path)
            original_list_sessions = vibe_training_store.list_sessions
            with patch.object(vibe_retrieval.vts, "list_sessions", side_effect=lambda limit=250: original_list_sessions(limit=limit, db_path=db_path)):
                examples = vibe_retrieval.retrieve_session_examples("dusty funk", limit=2)

        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["prompt"], "dusty funk drums")

    def test_library_hints_handles_tag_db_failure(self):
        with patch("vibe_retrieval.fetch_samples.load_tag_db", side_effect=ValueError("bad tag db")):
            hints = vibe_retrieval.library_hints("dusty funk", limit=3)

        self.assertEqual(hints, {"type_codes": [], "genres": [], "vibes": []})


class PersonalizedApiTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(REPO_DIR=REPO_ROOT, TOOL_PATH_PREFIX="", LLM_TIMEOUT=30)
        self.app.register_blueprint(vibe_bp, url_prefix="/api")
        self.client = self.app.test_client()

    def test_generate_vibe_returns_session_id(self):
        script_output = {"prompt": "dusty", "parsed": {"keywords": ["dusty"]}, "draft_preset": {"pads": {1: "KIK dusty one-shot"}}}
        with patch("api.vibe.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(script_output), stderr="")), patch("api.vibe.vts.create_session", return_value="session-123"):
            response = self.client.post("/api/vibe/generate", json={"prompt": "dusty"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["session_id"], "session-123")

    def test_apply_bank_logs_reviewed_parsed(self):
        thread_calls = {}

        class FakeThread:
            daemon = False

            def __init__(self, target=None, args=None):
                thread_calls["args"] = args

            def start(self):
                thread_calls["started"] = True

        with patch("api.vibe.threading.Thread", FakeThread), patch("api.vibe.vts.update_review") as update_review:
            response = self.client.post(
                "/api/vibe/apply-bank",
                json={
                    "session_id": "session-123",
                    "bank": "b",
                    "fetch": False,
                    "reviewed_parsed": {"keywords": "dusty, funk", "type_code": "BRK"},
                    "preset": {"name": "Draft", "pads": {1: "KIK dusty one-shot"}, "vibe": "dusty funk"},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(thread_calls["started"])
        update_review.assert_called_once()
        reviewed_parsed = update_review.call_args[0][2]
        self.assertEqual(reviewed_parsed["keywords"], ["dusty", "funk"])


class ParserModeTests(unittest.TestCase):
    def test_parse_vibe_prompt_uses_retrieval_context_in_rag_mode(self):
        with patch.dict(vibe_generate.SETTINGS, {"VIBE_PARSER_MODE": "rag", "VIBE_RETRIEVAL_LIMIT": 2}, clear=False), patch("vibe_generate.build_retrieval_context", return_value={"historical_examples": [{"prompt": "dusty funk"}]}) as retrieval_mock, patch("vibe_generate._call_llm", return_value={"keywords": ["dusty"], "type_code": None, "playability": None, "vibe": [], "genre": [], "texture": [], "energy": [], "rationale": ""}):
            result = vibe_generate.parse_vibe_prompt("dusty")

        retrieval_mock.assert_called_once()
        self.assertEqual(result["model_mode"], "rag")
        self.assertIn("historical_examples", result["retrieval_context"])


class EvalRunnerTests(unittest.TestCase):
    def test_evaluate_ranking_uses_fixture_library(self):
        summary, details = vibe_eval_model.evaluate_ranking(
            os.path.join(REPO_ROOT, "data", "evals", "prompt_to_ranking.jsonl"),
            os.path.join(REPO_ROOT, "data", "evals", "ranking_fixture.json"),
        )

        self.assertEqual(summary["cases"], 6)
        self.assertGreaterEqual(summary["top1_accuracy"], 0.5)
        self.assertEqual(len(details), 6)

    def test_prepare_dataset_builds_parse_and_draft_examples(self):
        rows = [
            {
                "id": "session-1",
                "prompt": "dusty funk",
                "bpm": 110,
                "musical_key": "Am",
                "parsed_json": json.dumps({"keywords": ["dusty"]}),
                "reviewed_parsed_json": json.dumps({"keywords": ["dusty", "funk"]}),
                "draft_preset_json": json.dumps({"pads": {"1": "KIK dusty one-shot"}}),
                "reviewed_preset_json": json.dumps({"pads": {"1": "KIK dusty funk one-shot"}}),
                "applied_preset_json": None,
            }
        ]
        parse_rows, draft_rows = vibe_prepare_dataset.build_examples(rows)

        self.assertEqual(len(parse_rows), 1)
        self.assertEqual(parse_rows[0]["output"]["keywords"], ["dusty", "funk"])
        self.assertEqual(len(draft_rows), 1)

    def test_train_lora_resolves_repo_relative_paths(self):
        resolved = vibe_train_lora._resolve_repo_path("data/training/vibe/parse_train.jsonl")

        self.assertTrue(resolved.endswith("data/training/vibe/parse_train.jsonl"))
        self.assertTrue(os.path.isabs(resolved))


if __name__ == "__main__":
    unittest.main()
