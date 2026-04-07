"""Sanity-check that configured paths point at a real library on this machine.

Unit tests use temp dirs; this file ties pytest to your actual SP404 library when
it exists. On CI or a fresh clone without ~/Music/SP404-Sample-Library, tests skip.
"""

from __future__ import annotations

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import jambox_config  # noqa: E402


def _settings():
    return jambox_config.load_settings_for_script(os.path.join(SCRIPTS, "fetch_samples.py"))


class LiveLibraryPathTests(unittest.TestCase):
    """Verify jambox_config resolves to an on-disk library + tag store when present."""

    def test_sample_library_directory_exists(self):
        lib = _settings()["SAMPLE_LIBRARY"]
        if not os.path.isdir(lib):
            self.skipTest(f"SAMPLE_LIBRARY not on this machine: {lib}")
        # Readable root (SD-card builder expects FLAC tree under here)
        self.assertTrue(os.access(lib, os.R_OK), f"not readable: {lib}")

    def test_tag_database_backing_store_exists(self):
        s = _settings()
        lib = s["SAMPLE_LIBRARY"]
        tags_file = s["TAGS_FILE"]
        if not os.path.isdir(lib):
            self.skipTest(f"SAMPLE_LIBRARY not on this machine: {lib}")
        sqlite_path = os.path.splitext(tags_file)[0] + ".sqlite"
        json_exists = os.path.isfile(tags_file)
        sqlite_exists = os.path.isfile(sqlite_path)
        self.assertTrue(
            json_exists or sqlite_exists,
            f"expected _tags.json or {os.path.basename(sqlite_path)} under {lib}",
        )


if __name__ == "__main__":
    unittest.main()
