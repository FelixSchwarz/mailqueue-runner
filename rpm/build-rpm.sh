#!/bin/sh
# Build RPMs with mock from the src.rpm in "rpm/build/" (see "rpm/build-srpm.sh").
#
# usage: build-rpm.sh <COPR chroot> [MOCK ARGS...]
#        e.g. build-rpm.sh epel-9-x86_64
#
# Like in COPR, packages from the COPR project (e.g. smtpproto, schwarzlog) are
# available as dependencies. The RPMs end up in "rpm/build/<COPR chroot>/".

set -eu

cd "$(dirname "$0")/.."
chroot="$1"
shift

# mock has no plain "epel-*" configuration
case "$chroot" in
    epel-*) mock_root="alma+$chroot" ;;
    *)      mock_root="$chroot" ;;
esac

# "%check" installs some test dependencies via pip so network is needed
mock --root="$mock_root" \
    --enable-network \
    --addrepo="https://download.copr.fedorainfracloud.org/results/fschwarz/mailqueue-runner/$chroot/" \
    --resultdir="rpm/build/$chroot" \
    "$@" \
    --rebuild rpm/build/*.src.rpm
