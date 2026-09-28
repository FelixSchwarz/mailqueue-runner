# query OSV for known malware before syncing
export UV_MALWARE_CHECK := "1"

# running plain "just" should not trigger a recipe, default to listing all recipes
[private]
default:
    @just --list --unsorted

# run the test suite
[group("development")]
run-tests:
    uv run --locked --extra testing pytest

# check the type annotations with ty
[group("development")]
check-types:
    uv run --locked --group quality --all-extras ty check schwarz tests

# create/update the project virtualenv with all extras and the quality tools
[group("development")]
setup-venv:
    uv sync --locked --all-extras --group=quality

# build wheel and sdist in "dist/"
[group("packaging")]
build:
    uv build --wheel --sdist --build-constraint build-constraints.txt --require-hashes

# create a src.rpm in "rpm/build/" from the sdist in "dist/" (see "just build")
[group("rpm")]
build-srpm:
    rpm/build-srpm.sh

# build RPMs with mock from the src.rpm in "rpm/build/", e.g. "just build-rpm epel-9-x86_64"
[group("rpm")]
[positional-arguments]
build-rpm chroot *MOCK_ARGS:
    rpm/build-rpm.sh "$@"

# install the build backend pinned by the current lockfile
[group("dependencies")]
install-locked-dependencies:
    uv sync --locked --only-group build

# Build isolation deliberately does not use "uv.lock". Export the locked build
# backend and pass the resulting, hashed constraints to "uv build" instead.
[doc('update "uv.lock" and "build-constraints.txt" to the latest versions')]
[group("dependencies")]
update-dependencies:
    uv lock --upgrade
    uv export --frozen --only-group build --output-file build-constraints.txt > /dev/null

# update the pinned prek hooks (with a 7 day cooldown)
[group("dependencies")]
update-prek-hooks:
    uv run --group quality prek update --freeze --cooldown-days=7

# Stays within the current major version unless "--allow-major-upgrades" is used.
[doc('pin GitHub Actions in ".github/workflows" to the latest commit sha')]
[group("dependencies")]
update-workflow-actions *ARGS:
    ./tools/update-workflow-actions.py --cooldown-days=7 {{ARGS}}
