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

# Build isolation deliberately does not use "uv.lock". Export the locked build
# backend and pass the resulting, hashed constraints to "uv build" instead.
update-build-constraints:
    uv lock --upgrade-package hatchling
    uv export --frozen --only-group build --output-file build-constraints.txt

build:
    uv build --wheel --sdist --build-constraint build-constraints.txt --require-hashes

# pin GitHub Actions in ".github/workflows" to the latest commit sha
# (stays within the current major version unless "--allow-major-upgrades"
# is used)
update-workflow-actions *ARGS:
    ./tools/update-workflow-actions.py --cooldown-days=7 {{ARGS}}

update-prek-hooks:
    uv run --group quality prek update --freeze --cooldown-days=7
