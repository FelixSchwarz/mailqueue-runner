# query OSV for known malware before syncing
export UV_MALWARE_CHECK := "1"

# install the build backend pinned by the current lockfile
install-locked-dependencies:
    uv sync --locked --only-group build

# update "uv.lock" to the latest versions
update-dependencies:
    uv lock --upgrade

# create/update the project virtualenv with the locked test and color extras
setup-venv:
    uv sync --locked --extra testing --extra colors

test:
    uv run --locked --extra testing pytest

update-prek-hooks:
    uv run --group quality prek update --freeze --cooldown-days=7
