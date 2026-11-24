# Publishing a release

The release workflow publishes the tagged source to PyPI and then creates a
GitHub release with the same wheel and source archive. Tags must be the exact
library version prefixed with `v`: version `0.1.0` requires tag `v0.1.0`.

## Configure trusted publishing

Configure these settings once in the GitHub repository that contains this
project:

1. Enable GitHub Actions and create an environment named `pypi` under
   **Settings → Environments**. Environment reviewers are optional; if enabled,
   the publishing job waits for their approval.
2. In the PyPI project settings, add a trusted publisher for GitHub Actions.
   For a first release, use PyPI's pending-publisher setup to create the project
   through that publisher.
3. Set the publisher's owner and repository name to the actual GitHub owner
   and repository containing this code. Set the workflow filename to
   `release.yml` and the environment name to `pypi`.
4. Confirm the PyPI project name is `skport-py` and that your account can manage
   that project or register the pending publisher.

The workflow exchanges GitHub's short-lived identity token for permission to
publish. It does not require a stored PyPI API token. The GitHub release job
uses the workflow's `GITHUB_TOKEN`; only that job requests repository write
permission.

## Prepare a version

Update `src/skport/_version.py` to the intended version, then commit the release
changes. The version must use canonical [PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/)
notation. For example, use `0.2.0rc1` for a release candidate and tag it
`v0.2.0rc1`. Release candidates and other prereleases are marked as prereleases
on GitHub. Local version suffixes such as `+test` are rejected.

Run the project checks and inspect a local package build before pushing a tag:

```bash
python -m pip install -e ".[dev]" twine packaging
python -m pytest -q
python -m ruff check src examples
python -m mypy src/skport
python -m unittest discover -s .github/scripts -p test_release.py
python -m build
python -m twine check dist/*
python .github/scripts/release.py check-tag --tag v0.1.0
```

Use the version you are preparing in the validation command. PyPI versions are
immutable: choose a new version for every new publication.

## Push the release tag

Once the version change is committed and pushed, create and push its tag:

```bash
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

The tag triggers `.github/workflows/release.yml`. A tag mismatch fails before
package building or publishing begins. The workflow then:

1. Validates the tag and tests the release-validation helper.
2. Builds one wheel and one source archive.
3. Checks package metadata, filenames and versions against the library version.
4. Records SHA-256 checksums and carries those verified files between jobs.
5. Publishes the distributions to PyPI using the `pypi` environment.
6. Creates a GitHub release with generated notes, both distributions and
   `SHA256SUMS`.

The release appears only after PyPI publishing succeeds. The workflow uses
tracked release-helper tests, so it does not depend on the ignored local test
folder or account credentials.

## Recover a failed run

Read the failed job's output in **Actions**. Correct a version mismatch before
creating the intended tag. For a failed PyPI publishing job, verify the trusted
publisher's repository, workflow and environment settings.

If PyPI publishing succeeded and only the GitHub release job failed, rerun the
failed job instead of publishing the same PyPI version again. The release job
can upload files to an existing release for the tag. A full rerun will attempt
the PyPI upload again and an already-published version is rejected.

Do not move a published release tag to different source code. Prepare a new
version and tag when the package itself needs a correction.

[Back to the documentation overview](../overview.md)
