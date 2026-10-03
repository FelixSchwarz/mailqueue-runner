#!/bin/sh
# Build RPMs with mock from a src.rpm (e.g. the one in "rpm/build/" created by
# "rpm/build-srpm.sh" or one attached to a GitHub release).
#
# usage: build-rpm.sh <COPR chroot> <src.rpm> [MOCK ARGS...]
#        e.g. build-rpm.sh epel-9-x86_64 rpm/build/mailqueue-runner-1.0.0-1.fc44.src.rpm
#
# Like in COPR, packages from the COPR project (e.g. smtpproto, schwarzlog) are
# available as dependencies. The RPMs end up in "rpm/build/<COPR chroot>/".

set -eu

chroot="$1"
# resolved before changing the directory so relative paths keep working
srpm=$(realpath "$2")
shift 2

cd "$(dirname "$0")/.."

# mock has no plain "epel-*" configuration
case "$chroot" in
    epel-*) mock_root="alma+$chroot" ;;
    *)      mock_root="$chroot" ;;
esac

mock --root="$mock_root" \
    --addrepo="https://download.copr.fedorainfracloud.org/results/fschwarz/mailqueue-runner/$chroot/" \
    --resultdir="rpm/build/$chroot" \
    "$@" \
    --rebuild "$srpm"
