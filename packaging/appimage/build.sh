#!/bin/bash
set -e

TAG="$1"
PKGREL="${2:-1}"
if [ -z "$TAG" ]; then
    echo "Usage: $0 <release-tag> [package-release]" >&2
    echo "Example: $0 2.0.0 1" >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

APP_ID="io.github.Faugus.faugus-launcher"
REPO_URL="https://github.com/Faugus/faugus-launcher"
VERSION="$TAG-$PKGREL"
ARCH=$(uname -m)

BUILD_ROOT="$SCRIPT_DIR/appimage-build"
RELEASE_TAR="$BUILD_ROOT/faugus-launcher-$TAG.tar.gz"
RELEASE_SRC_ROOT="$BUILD_ROOT/release-src"
MESON_BUILD_DIR="$BUILD_ROOT/build"
APPDIR="$BUILD_ROOT/AppDir"
TOOLS_DIR="$SCRIPT_DIR/.appimage-tools"
APPIMAGETOOL="$TOOLS_DIR/appimagetool-$ARCH.AppImage"
OUTPUT="$SCRIPT_DIR/Faugus-$VERSION-$ARCH.AppImage"

for cmd in meson ninja python3 curl tar; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Missing required tool: $cmd" >&2
        exit 1
    fi
done

if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "pip for python3 is required to bundle dependencies (requests, psutil, vdf, Pillow, icoextract, pefile, dbus-python)." >&2
    echo "Install it first, e.g. on Arch: sudo pacman -S python-pip" >&2
    exit 1
fi

echo "This AppImage bundles Faugus's own Python code and its pip-only"
echo "dependencies. It relies on the host system for Python 3, GTK4,"
echo "libadwaita, libmanette and PyGObject, since fully bundling those"
echo "is impractical for a GTK4 app. Target systems need those installed."
echo

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$RELEASE_SRC_ROOT" "$TOOLS_DIR"

echo "Downloading release $TAG..."
curl -fL -o "$RELEASE_TAR" "$REPO_URL/archive/refs/tags/$TAG.tar.gz"

tar -xzf "$RELEASE_TAR" -C "$RELEASE_SRC_ROOT"
SOURCE_DIR=$(find "$RELEASE_SRC_ROOT" -mindepth 1 -maxdepth 1 -type d)
if [ -z "$SOURCE_DIR" ]; then
    echo "Could not find extracted source directory" >&2
    exit 1
fi

cleanup() {
    rm -rf "$RELEASE_TAR" "$RELEASE_SRC_ROOT"
}
trap cleanup EXIT

meson setup "$MESON_BUILD_DIR" "$SOURCE_DIR" --prefix=/usr
ninja -C "$MESON_BUILD_DIR"
DESTDIR="$APPDIR" ninja -C "$MESON_BUILD_DIR" install

PY_TAG=$(python3 -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}")')
VENDOR_DIR="$APPDIR/usr/lib/$PY_TAG/site-packages"
mkdir -p "$VENDOR_DIR"
python3 -m pip install --target="$VENDOR_DIR" --no-compile \
    requests psutil vdf Pillow icoextract pefile dbus-python

DESKTOP_SRC="$APPDIR/usr/share/applications/$APP_ID.desktop"
ICON_SVG_SRC="$APPDIR/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
ICON_PNG_SRC="$SOURCE_DIR/assets/faugus-launcher-raster.png"

cp "$DESKTOP_SRC" "$APPDIR/$APP_ID.desktop"
cp "$ICON_SVG_SRC" "$APPDIR/$APP_ID.svg"
cp "$ICON_PNG_SRC" "$APPDIR/$APP_ID.png"
ln -sf "$APP_ID.png" "$APPDIR/.DirIcon"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/bash
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

for site_packages in "$HERE"/usr/lib/python3*/site-packages; do
    export PYTHONPATH="$site_packages${PYTHONPATH:+:$PYTHONPATH}"
done

export XDG_DATA_DIRS="$HERE/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

case "$1" in
    --shortcut) shift; exec python3 -m faugus.shortcut "$@";;
    --game)     shift; exec python3 -m faugus.runner --game "$@";;
    --run)      shift; msg="$1"; shift; exec python3 -m faugus.runner "$msg" "$@";;
    *)          exec python3 -m faugus.launcher "$@";;
esac
APPRUN
chmod +x "$APPDIR/AppRun"

if [ ! -x "$APPIMAGETOOL" ]; then
    curl -L -o "$APPIMAGETOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

rm -f "$OUTPUT"
ARCH="$ARCH" "$APPIMAGETOOL" "$APPDIR" "$OUTPUT"

echo
echo "Built: $OUTPUT"
