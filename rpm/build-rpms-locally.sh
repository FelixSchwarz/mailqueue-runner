#!/bin/sh
# Build the RPMs for mailqueue-runner and its dependencies which are not
# packaged in Fedora/EPEL (smtpproto, schwarzlog) with mock without using COPR.
#
# usage: build-rpms-locally.sh <mock config>
#        e.g. build-rpms-locally.sh alma+epel-9-x86_64
#
# Expects the mailqueue-runner src.rpm in "rpm/build/" (see "rpm/build-srpm.sh").
# Each dependency sdist is verified against "rpm/<name>-<version>.tar.gz.sha256".
# "mock --chain" builds the dependencies first and provides them to the
# mailqueue-runner build via a local repository in "rpm/build/repo-<mock config>/".

set -eu

cd "$(dirname "$0")/.."
mock_root="$1"
build_dir="$PWD/rpm/build"

for name in smtpproto schwarzlog; do
    spec="$PWD/rpm/python-$name.spec"
    version=$(rpmspec -q --srpm --queryformat '%{version}' "$spec")
    checksum_file="$PWD/rpm/$name-$version.tar.gz.sha256"

    spectool -g -C "$build_dir" "$spec"
    (cd "$build_dir" && sha256sum -c "$checksum_file")
    rpmbuild -bs \
        --define "_sourcedir $build_dir" \
        --define "_srcrpmdir $build_dir" \
        --define "dist %{nil}" \
        "$spec"
done

mock --root="$mock_root" \
    --chain --localrepo="$build_dir/repo-$mock_root" \
    "$build_dir"/python-smtpproto-*.src.rpm \
    "$build_dir"/python-schwarzlog-*.src.rpm \
    "$build_dir"/mailqueue-runner-*.src.rpm
