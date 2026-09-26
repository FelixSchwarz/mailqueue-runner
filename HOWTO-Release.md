# Releases

Releases are built by the `Create Release Artifacts` workflow, not locally. It
runs the test suite against `uv.lock`, builds wheel and sdist with the
hash-pinned build backend from `build-constraints.txt`, builds an SRPM from the
sdist, rebuilds that SRPM with mock (COPR repo enabled), attests the build provenance, attaches the artifacts to a GitHub release
and uploads the wheel and sdist to PyPI via trusted publishing. The SRPM is
attached only to the GitHub release.

1. Optionally refresh pinned dependencies and tooling:

   ```console
   $ just update-dependencies
   $ just update-prek-hooks
   $ just update-workflow-actions
   ```

   `just update-dependencies` also regenerates `build-constraints.txt`.

2. Set the release version in `VERSION.txt`, update `Version` and `%changelog`
   in `rpm/mailqueue-runner.spec`, then commit both files.

3. Push the tag to trigger the release workflow:

   ```console
   $ git tag "v$(cat VERSION.txt)"
   $ git push origin main "v$(cat VERSION.txt)"
   ```

4. Approve the deployment to the `pypi` environment in the workflow run. This
   publishes the artifacts to PyPI and GitHub.

5. Build the SRPM attached to the GitHub release in COPR:

   ```console
   $ copr-cli build fschwarz/mailqueue-runner mailqueue-runner-*.src.rpm
   ```

6. Set the next development version in `VERSION.txt` and commit it.

`just build` produces the same wheel and sdist locally, for example to test the
packaging. `just build-srpm` and `just build-rpm <mock chroot>` build the RPM
locally.
