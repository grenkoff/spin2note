"""Archive extraction for bulk upload.

One engine (``libarchive``) reads zip, rar, 7z, tar and tar.gz/bz2/xz, so users can upload a
single archive of their whole base instead of selecting files. We pull out the ``.txt`` members
(hand histories + tournament summaries) and hand them to the normal parse pipeline.
"""

from __future__ import annotations

from collections.abc import Iterator

# Extensions routed to server-side extraction (vs the client-side .txt bundling path).
ARCHIVE_SUFFIXES = (".zip", ".rar", ".7z", ".tar", ".tar.gz", ".tgz", ".gz", ".bz2", ".xz")


def is_archive(filename: str) -> bool:
    name = filename.lower()
    return any(name.endswith(s) for s in ARCHIVE_SUFFIXES)


def extract_text_members(data: bytes) -> Iterator[tuple[str, str]]:
    """Yield (name, text) for every ``.txt`` file inside an archive blob."""
    import libarchive  # imported lazily; needs the system libarchive shared lib

    with libarchive.memory_reader(data) as archive:
        for entry in archive:
            if not entry.isfile:
                continue
            name = str(entry.pathname)
            if not name.lower().endswith(".txt"):
                continue
            raw = b"".join(entry.get_blocks())
            yield name, raw.decode("utf-8", errors="replace")
