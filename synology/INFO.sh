#!/bin/sh
# INFO.sh
. /pkgscripts/include/pkg_util.sh

package="tricerapost"
version="0.1.0-0001"
os_min_ver="7.0-40000"
displayname="TriceraPost"
description="Private, self-hosted Usenet indexer for NNTP binaries."
arch="noarch"
maintainer="TriceraPost"
startable="yes"
install_dep_packages="Python3"

pkg_dump_info
