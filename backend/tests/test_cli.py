"""Tests for CLI helper functions in backend/cli.py."""
import hashlib
import os

import pytest
import sys

# cli.py lives in the backend directory, not in a package, so we add it to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cli import _slug, _hash_file


class TestSlug:
    def test_lowercase(self):
        assert _slug("Zelda") == "zelda"

    def test_spaces_become_hyphens(self):
        assert _slug("The Legend of Zelda") == "the-legend-of-zelda"

    def test_special_chars_removed(self):
        assert _slug("Mario & Luigi: SuperStar!") == "mario-luigi-superstar"

    def test_consecutive_separators_collapsed(self):
        assert _slug("Zelda  --  BOTW") == "zelda-botw"

    def test_leading_trailing_hyphens_stripped(self):
        assert _slug("--Zelda--") == "zelda"

    def test_numbers_preserved(self):
        assert _slug("Final Fantasy 7") == "final-fantasy-7"

    def test_already_slug(self):
        assert _slug("zelda-botw") == "zelda-botw"

    def test_empty_string(self):
        assert _slug("") == ""

    def test_only_special_chars(self):
        assert _slug("!@#$%") == ""


class TestHashFile:
    def test_hash_matches_sha256(self, tmp_path):
        f = tmp_path / "save.sav"
        data = b"some binary save data"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert _hash_file(str(f)) == expected

    def test_hash_empty_file(self, tmp_path):
        f = tmp_path / "empty.sav"
        f.write_bytes(b"")
        assert _hash_file(str(f)) == hashlib.sha256(b"").hexdigest()

    def test_hash_missing_file_returns_empty_string(self, tmp_path):
        missing = str(tmp_path / "nonexistent.sav")
        assert _hash_file(missing) == ""

    def test_hash_large_file(self, tmp_path):
        f = tmp_path / "large.sav"
        data = b"x" * (8192 * 5)  # multiple chunks
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert _hash_file(str(f)) == expected

    def test_different_files_have_different_hashes(self, tmp_path):
        f1 = tmp_path / "a.sav"
        f2 = tmp_path / "b.sav"
        f1.write_bytes(b"aaa")
        f2.write_bytes(b"bbb")
        assert _hash_file(str(f1)) != _hash_file(str(f2))
