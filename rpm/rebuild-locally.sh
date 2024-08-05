#!/bin/sh

set -u

rm -f *.src.rpm

set -e

fedpkg --release=epel9 srpm
mock -r alma+epel-9-x86_64 --rebuild --enable-network *.src.rpm
