import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path

from cttir_model.errors import ProjectError
from cttir_model.sources import extract_candidates, read_archive


def archive(path, items):
    with tarfile.open(path, "w:gz") as output:
        for name, raw in items:
            entry = tarfile.TarInfo(name)
            entry.size = len(raw)
            output.addfile(entry, io.BytesIO(raw))


class ArchiveTests(unittest.TestCase):
    def test_traversal_links_and_expansion_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.tar.gz"
            for name in ["../secret", "/absolute", "x\\bad"]:
                archive(path, [(name, b"x")])
                with self.assertRaises(ProjectError):
                    read_archive(path)
            archive(path, [("ok", b"x" * 2048)])
            with self.assertRaises(ProjectError):
                read_archive(path, 1024)
            with tarfile.open(path, "w:gz") as output:
                entry = tarfile.TarInfo("symlink")
                entry.type, entry.linkname = tarfile.SYMTYPE, "/etc/passwd"
                output.addfile(entry)
            with self.assertRaises(ProjectError):
                read_archive(path)

    @unittest.skipUnless(os.environ.get("CTTIR_TEST_SANDBOX") == "1", "Explicit Linux R sandbox tier")
    def test_rd_import_remains_candidate_and_rejects_dynamic_macros(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.tar.gz"
            archive(path, [("demo/DESCRIPTION", b"Package: demo\nVersion: 1.0\nLicense: MIT\n"),
                           ("demo/NAMESPACE", b"export(align)\n"),
                           ("demo/man/align.Rd", b"\\name{align}\n\\alias{align}\n\\title{Align rows}\n\\description{Preserve identifiers.}\n\\usage{align(x, ids)}\n"),
                           ("demo/man/dynamic.Rd", b"\\name{bad}\n\\title{Bad}\n\\description{\\Sexpr{system('bad')}}\n")])
            result = extract_candidates(path, "synthetic")
            self.assertEqual(len(result["corpus"]["documents"]), 1)
            self.assertEqual(result["corpus"]["documents"][0]["review_status"], "candidate")
            self.assertEqual(result["corpus"]["documents"][0]["rights_status"], "pending")
            self.assertEqual(len(result["source"]["failures"]), 1)
