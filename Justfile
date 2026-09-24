# query OSV for known malware before syncing
export UV_MALWARE_CHECK := "1"

# install the build backend pinned by the current lockfile
install-locked-dependencies:
    uv sync --locked --only-group build

# update "uv.lock" to the latest versions
update-dependencies:
    uv lock --upgrade

test:
    uv run --locked --extra testing pytest
