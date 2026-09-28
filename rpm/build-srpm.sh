#!/bin/sh
# Create a src.rpm in "rpm/build/" from the sdist in "dist/" (see "just build").
# The spec file always matches VERSION.txt ("tools/check-rpm-version.py") so the
# sdist file name can be derived from VERSION.txt.

set -eu

cd "$(dirname "$0")/.."
build_dir="$PWD/rpm/build"

# "trash" is only needed locally as CI always starts with a fresh checkout
if [ -d "$build_dir" ]; then
    trash "$build_dir"
fi
mkdir "$build_dir"
cp -a "dist/mailqueue_runner-$(cat VERSION.txt).tar.gz" \
    rpm/mailqueue-runner.conf rpm/mailqueue-runner.logrotate \
    "$build_dir/"
rpmbuild -bs \
    --define "_sourcedir $build_dir" \
    --define "_srcrpmdir $build_dir" \
    rpm/mailqueue-runner.spec
