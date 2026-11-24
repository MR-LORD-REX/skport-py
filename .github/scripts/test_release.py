"""Release checks run in CI without the ignored local test suite."""

from __future__ import annotations

import hashlib
import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from release import check_distributions, check_tag, read_project, write_checksums


class ReleaseValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def source(self, version: str, *, definition: str | None = None) -> Path:
        (self.root / "src/skport").mkdir(parents=True, exist_ok=True)
        (self.root / "pyproject.toml").write_text('[project]\nname = "skport-py"\n', encoding="utf-8")
        (self.root / "src/skport/_version.py").write_text(
            definition if definition is not None else f'__version__ = "{version}"\n', encoding="utf-8"
        )
        return self.root

    def distributions(self, *, wheel_version: str = "0.1.0", source_version: str = "0.1.0") -> Path:
        directory = self.root / "dist"
        directory.mkdir()
        with zipfile.ZipFile(directory / "skport_py-0.1.0-py3-none-any.whl", "w") as archive:
            archive.writestr(
                "skport_py-0.1.0.dist-info/METADATA",
                f"Metadata-Version: 2.4\nName: skport-py\nVersion: {wheel_version}\n\n",
            )
        metadata = f"Metadata-Version: 2.4\nName: skport-py\nVersion: {source_version}\n\n".encode()
        with tarfile.open(directory / "skport_py-0.1.0.tar.gz", "w:gz") as archive:
            member = tarfile.TarInfo("skport_py-0.1.0/PKG-INFO")
            member.size = len(metadata)
            archive.addfile(member, io.BytesIO(metadata))
        return directory

    def test_tag_matches_a_literal_library_version_without_importing_sdk(self) -> None:
        root = self.source(
            "0.1.0", definition='raise RuntimeError("must not import")\n__version__ = "0.1.0"\n'
        )
        name, version = read_project(root)
        self.assertEqual((name, version), ("skport-py", "0.1.0"))
        check_tag("v0.1.0", version)

    def test_wrong_or_unprefixed_tag_fails(self) -> None:
        for tag in ("v0.1.1", "0.1.0", "vlatest", "v0.1.0\n"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                check_tag(tag, "0.1.0")

    def test_invalid_noncanonical_and_local_versions_fail(self) -> None:
        for version in ("not-a-version", "v0.1.0", "0.1.0-rc1", "0.1.0+test"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                read_project(self.source(version))

    def test_canonical_release_candidate_is_supported(self) -> None:
        _, version = read_project(self.source("0.2.0rc1"))
        check_tag("v0.2.0rc1", version)

    def test_dynamic_or_duplicate_version_definition_fails(self) -> None:
        definitions = ("__version__ = str(1)\n", '__version__ = "0.1.0"\n__version__ = "0.2.0"\n')
        for definition in definitions:
            with self.subTest(definition=definition), self.assertRaises(ValueError):
                read_project(self.source("", definition=definition))

    def test_matching_wheel_and_source_archive_have_verified_checksums(self) -> None:
        directory = self.distributions()
        files = check_distributions(directory, "skport-py", "0.1.0")
        destination = self.root / "SHA256SUMS"
        digest = write_checksums(files, destination)
        self.assertEqual(digest, hashlib.sha256(destination.read_bytes()).hexdigest())
        self.assertEqual(
            destination.read_text().splitlines(),
            [f"{hashlib.sha256(file.read_bytes()).hexdigest()}  dist/{file.name}" for file in files],
        )

    def test_wheel_metadata_version_mismatch_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "distribution version"):
            check_distributions(self.distributions(wheel_version="0.2.0"), "skport-py", "0.1.0")

    def test_source_metadata_version_mismatch_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "distribution version"):
            check_distributions(self.distributions(source_version="0.2.0"), "skport-py", "0.1.0")

    def test_filename_version_mismatch_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "filename"):
            check_distributions(self.distributions(), "skport-py", "0.2.0")

    def test_unexpected_release_files_fail(self) -> None:
        directory = self.distributions()
        (directory / "extra.whl").write_bytes(b"unexpected")
        with self.assertRaisesRegex(ValueError, "exactly one wheel"):
            check_distributions(directory, "skport-py", "0.1.0")


if __name__ == "__main__":
    unittest.main()
