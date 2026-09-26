# Release checklist

1. Run `bash tests/run.sh` from the repository root. All checks must pass.
2. Confirm GitHub Actions passes for the exact commit being released.
3. Smoke-test the README installation in a fresh tmux server using only the documented setup.
4. Review `git status --short`: include new tests and documentation; exclude generated files and local operational notes.
5. Update CHANGELOG.md with the release version/date and any upgrade instructions.
6. Confirm the tested platform/version matrix matches CI. Do not imply support for untested platforms.
7. Commit the release contents, review the diff, and create a version tag.
8. Publish the release and announcement only after the above gates pass.

For a local TPM installation check, run
`python3 tests/tpm_install.py /path/to/tpm`. This uses the real TPM scripts
with a disposable snapshot of the working tree, temporary home, and private
tmux server. It checks install, reload, view providers, removal, and manual
installation without modifying the user's configuration. It does not test
GitHub downloads or credentials.

On macOS, named agent process fixtures additionally require Homebrew coreutils
(`gsleep`); Apple's protected system `sleep` cannot serve as a renamed executable.

For demonstrations, use fixture sessions and panes rather than terminal captures containing private project names or output.
