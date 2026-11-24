"""Validate release tags and distribution metadata before publishing."""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

from packaging.utils import canonicalize_name, parse_sdist_filename, parse_wheel_filename
from packaging.version import InvalidVersion, Version


def read_project(root: Path) -> tuple[str, str]:
    """Read the version literal without importing the SDK or its dependencies."""
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    tree = ast.parse((root / "src/skport/_version.py").read_text(encoding="utf-8"))
    definitions = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)
    ]
    if len(definitions) != 1 or not isinstance(definitions[0], ast.Constant):
        raise ValueError("__version__ must have exactly one literal string definition")
    literal = definitions[0].value
    if not isinstance(literal, str):
        raise ValueError("__version__ must be a literal string")
    try:
        version = Version(literal)
    except InvalidVersion as exc:
        raise ValueError("__version__ must be a valid PEP 440 version") from exc
    if version.local is not None or str(version) != literal:
        raise ValueError("__version__ must be canonical PEP 440 without a local version suffix")
    return canonicalize_name(project["name"]), literal


def check_tag(tag: str, version: str) -> None:
    """Require the pushed tag to identify the exact library version."""
    expected = f"v{version}"
    if tag != expected:
        raise ValueError(f"release tag must be {expected!r}; received {tag!r}")


def check_metadata(payload: bytes, package_name: str, version: str, label: str) -> None:
    """Check package identity in built metadata before any upload."""
    metadata = BytesParser().parsebytes(payload)
    names = metadata.get_all("Name", [])
    versions = metadata.get_all("Version", [])
    if len(names) != 1 or canonicalize_name(names[0]) != canonicalize_name(package_name):
        raise ValueError(f"{label}: distribution name does not match {package_name!r}")
    if len(versions) != 1 or versions[0] != version:
        raise ValueError(f"{label}: distribution version does not match {version!r}")


def check_distributions(directory: Path, package_name: str, version: str) -> tuple[Path, Path]:
    """Require one matching wheel and source archive with consistent metadata."""
    files = sorted(directory.iterdir())
    wheels = [file for file in files if file.is_file() and file.suffix == ".whl"]
    sdists = [file for file in files if file.is_file() and file.name.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1 or len(files) != 2:
        raise ValueError(
            "distribution directory must contain exactly one wheel and one .tar.gz source archive"
        )
    wheel, sdist = wheels[0], sdists[0]
    for file, parser in ((wheel, parse_wheel_filename), (sdist, parse_sdist_filename)):
        parsed_name, parsed_version, *_ = parser(file.name)
        if parsed_name != canonicalize_name(package_name) or str(parsed_version) != version:
            raise ValueError(f"{file.name}: filename does not match the release package and version")
    with zipfile.ZipFile(wheel) as archive:
        entries = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(entries) != 1:
            raise ValueError("wheel must contain exactly one package METADATA file")
        check_metadata(archive.read(entries[0]), package_name, version, wheel.name)
    with tarfile.open(sdist, "r:gz") as archive:
        entries = [
            member
            for member in archive.getmembers()
            if len(Path(member.name).parts) == 2 and Path(member.name).name == "PKG-INFO" and member.isfile()
        ]
        if len(entries) != 1:
            raise ValueError("source archive must contain exactly one root package PKG-INFO file")
        handle = archive.extractfile(entries[0])
        if handle is None:
            raise ValueError("source archive package metadata cannot be read")
        with handle:
            check_metadata(handle.read(), package_name, version, sdist.name)
    return wheel, sdist


def write_checksums(files: tuple[Path, Path], destination: Path) -> str:
    """Write a manifest whose paths resolve inside the uploaded release artifact."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        f"{hashlib.sha256(file.read_bytes()).hexdigest()}  dist/{file.name}\n" for file in files
    )
    destination.write_text(payload, encoding="utf-8", newline="\n")
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def outputs(**values: str) -> None:
    """Expose validated values to later GitHub Actions jobs when applicable."""
    filename = os.environ.get("GITHUB_OUTPUT")
    if filename:
        with Path(filename).open("a", encoding="utf-8") as handle:
            for name, value in values.items():
                handle.write(f"{name}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    tag_parser = commands.add_parser("check-tag")
    tag_parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", ""))
    dist_parser = commands.add_parser("check-dist")
    dist_parser.add_argument("--directory", type=Path, default=Path("dist"))
    dist_parser.add_argument("--checksums", type=Path, default=Path("release-artifacts/SHA256SUMS"))
    args = parser.parse_args()
    try:
        package_name, version = read_project(args.root)
        if args.command == "check-tag":
            check_tag(args.tag, version)
            outputs(
                package_name=package_name,
                version=version,
                prerelease=str(Version(version).is_prerelease).lower(),
            )
            print(f"Verified {args.tag} matches {package_name} {version}")
        else:
            files = check_distributions(args.directory, package_name, version)
            checksum_sha256 = write_checksums(files, args.checksums)
            outputs(checksum_sha256=checksum_sha256)
            print(f"Verified wheel and source archive for {package_name} {version}")
    except (ValueError, KeyError, OSError, SyntaxError, tarfile.TarError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Release validation failed: {exc}\n")


if __name__ == "__main__":
    main()
