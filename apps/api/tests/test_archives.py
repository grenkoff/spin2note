"""Archive extraction: pull .txt members out of an archive blob."""

from __future__ import annotations

import io
import zipfile

import pytest

pytest.importorskip("libarchive")  # needs the system libarchive shared lib

from spin2note_api.ingest.archives import extract_text_members, is_archive  # noqa: E402


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_extracts_only_txt_members() -> None:
    blob = _zip(
        {
            "hands/GG1.txt": b"Poker Hand #SG1: ...",
            "summary/T1.txt": b"Tournament #1, Spin&Gold",
            "readme.md": b"not a hand history",
            "nested/dir/GG2.txt": b"Poker Hand #SG2: ...",
        }
    )
    members = dict(extract_text_members(blob))
    assert set(members) == {"hands/GG1.txt", "summary/T1.txt", "nested/dir/GG2.txt"}
    assert members["hands/GG1.txt"].startswith("Poker Hand #")


def test_is_archive_by_extension() -> None:
    assert is_archive("base.zip") and is_archive("HISTORY.RAR") and is_archive("x.tar.gz")
    assert not is_archive("GG20260101.txt")
