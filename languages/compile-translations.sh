#!/bin/sh
set -e

localedir="$1"
shift

for lang in "$@"; do
    po="$MESON_SOURCE_ROOT/languages/$lang/faugus-launcher.po"
    dest="$MESON_INSTALL_DESTDIR_PREFIX/$localedir/$lang/LC_MESSAGES"
    mkdir -p "$dest"
    msgfmt "$po" -o "$dest/faugus-launcher.mo"
done
