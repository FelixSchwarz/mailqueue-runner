# query OSV for known malware before syncing
export UV_MALWARE_CHECK := "1"

# install the build backend pinned by the current lockfile
install-locked-dependencies:
    uv sync --locked --only-group build

# update "uv.lock" to the latest versions
update-dependencies:
    uv lock --upgrade
    # Build isolation deliberately does not use "uv.lock". Export the locked build
    # backend and pass the resulting, hashed constraints to "uv build" instead.
    uv export --frozen --only-group build --output-file build-constraints.txt

# create/update the project virtualenv with the locked test and color extras
setup-venv:
    uv sync --locked --all-extras --group=quality

check-types:
    uv run --locked --group quality --all-extras ty check schwarz tests

test:
    uv run --locked --extra testing pytest

build:
    uv build --wheel --sdist --build-constraint build-constraints.txt --require-hashes

# COPR project which provides dependencies not packaged in Fedora/EPEL (e.g. smtpproto)
copr_project := "fschwarz/mailqueue-runner"

# create a src.rpm in "srpm/" from the sdist in "dist/" (see "just build")
build-srpm:
    #!/usr/bin/env bash
    # For release versions the spec file "Version" must match the sdist version
    # and the latest "%changelog" entry must mention "version-release".
    # Development versions (e.g. "0.14.0.dev0") are built with a patched copy of
    # the spec file.
    set -euo pipefail
    die() { echo "ERROR: $*" >&2; exit 1; }

    spec_name="mailqueue-runner.spec"
    spec="rpm/${spec_name}"
    shopt -s nullglob
    sdists=(dist/mailqueue_runner-*.tar.gz)
    shopt -u nullglob
    [ "${#sdists[@]}" -eq 1 ] || die "expected exactly one sdist in dist/, found ${#sdists[@]} (run \"just build\", remove stale sdists)"
    sdist=${sdists[0]}
    py_version=${sdist#dist/mailqueue_runner-}
    py_version=${py_version%.tar.gz}
    spec_version=$(rpmspec -q --srpm --qf '%{version}' "${spec}")

    topdir=$(mktemp -d)
    trap 'rm -rf "${topdir}"' EXIT
    mkdir "${topdir}/SOURCES" "${topdir}/SPECS"
    cp -a "${spec}" "${topdir}/SPECS/"
    cp -a "${sdist}" rpm/mailqueue-runner.conf rpm/mailqueue-runner.logrotate "${topdir}/SOURCES/"

    if [ "${spec_version}" = "${py_version}" ]; then
        evr=$(rpmspec -q --srpm --define 'dist %{nil}' --qf '%{version}-%{release}' "${spec}")
        changelog=$(rpmspec -q --srpm --qf '%{changelogname}' "${spec}")
        [[ "${changelog}" == *" - ${evr}" ]] \
            || die "latest %changelog entry in ${spec} (\"${changelog}\") does not match \"${evr}\""
    elif [[ "${py_version}" == *.dev* ]]; then
        echo "development version ${py_version}: building with patched spec file (Version: ${spec_version} -> ${py_version})"
        sed -i "s/^Version:.*/Version:        ${py_version}/" "${topdir}/SPECS/${spec_name}"
    else
        die "Version in ${spec} is \"${spec_version}\" but the Python package version is \"${py_version}\""
    fi

    rpmbuild --define "_topdir ${topdir}" -bs "${topdir}/SPECS/${spec_name}"
    rm -rf srpm
    mkdir srpm
    cp -a "${topdir}"/SRPMS/*.src.rpm srpm/

# build RPMs from the src.rpm in "srpm/" with mock, e.g. "just build-rpm alma+epel-9-x86_64"
build-rpm chroot *MOCK_ARGS:
    #!/usr/bin/env bash
    # Like COPR: packages from the COPR project are available as dependencies.
    # "%check" installs some test dependencies via pip so network is needed.
    set -euo pipefail
    chroot='{{ chroot }}'
    case "${chroot}" in
        # e.g. "alma+epel-9-x86_64" -> "epel-9-x86_64"
        *epel-*) copr_chroot="epel-${chroot#*epel-}" ;;
        *)       copr_chroot="${chroot}" ;;
    esac
    mock --root="${chroot}" --enable-network \
        --addrepo="https://download.copr.fedorainfracloud.org/results/{{ copr_project }}/${copr_chroot}/" \
        {{ MOCK_ARGS }} \
        --rebuild srpm/*.src.rpm

update-prek-hooks:
    uv run --group quality prek update --freeze --cooldown-days=7

# pin GitHub Actions in ".github/workflows" to the latest commit sha
# (stays within the current major version unless "--allow-major-upgrades"
# is used)
update-workflow-actions *ARGS:
    ./tools/update-workflow-actions.py --cooldown-days=7 {{ARGS}}
