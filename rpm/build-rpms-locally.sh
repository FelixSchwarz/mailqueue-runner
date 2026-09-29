#!/bin/sh
# Build the RPMs for mailqueue-runner and smtpproto with mock without using COPR.
#
# usage: build-rpms-locally.sh <mock config>
#        e.g. build-rpms-locally.sh alma+epel-9-x86_64
#
# Expects the mailqueue-runner src.rpm in "rpm/build/" (see "rpm/build-srpm.sh").
# The smtpproto sdist is verified against "rpm/smtpproto-<version>.tar.gz.sha256".
# "mock --chain" builds smtpproto first and provides it to the mailqueue-runner
# build via a local repository in "rpm/build/repo-<mock config>/".

set -eu

cd "$(dirname "$0")/.."
mock_root="$1"
build_dir="$PWD/rpm/build"
smtpproto_spec="$PWD/rpm/python-smtpproto.spec"
smtpproto_version=$(rpmspec -q --srpm --queryformat '%{version}' "$smtpproto_spec")
checksum_file="$PWD/rpm/smtpproto-$smtpproto_version.tar.gz.sha256"

spectool -g -C "$build_dir" "$smtpproto_spec"
(cd "$build_dir" && sha256sum -c "$checksum_file")
rpmbuild -bs \
    --define "_sourcedir $build_dir" \
    --define "_srcrpmdir $build_dir" \
    --define "dist %{nil}" \
    "$smtpproto_spec"

# "%check" of mailqueue-runner installs some test dependencies via pip
mock --root="$mock_root" \
    --enable-network \
    --chain --localrepo="$build_dir/repo-$mock_root" \
    "$build_dir"/python-smtpproto-*.src.rpm \
    "$build_dir"/mailqueue-runner-*.src.rpm
