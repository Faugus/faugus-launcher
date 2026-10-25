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
QUICK_SHARUN_URL="https://raw.githubusercontent.com/pkgforge-dev/Anylinux-AppImages/c28bb80743106fdf08cb10fb27d19d9932eb0865/useful-tools/quick-sharun.sh"
VERSION="$TAG-$PKGREL"
ARCH=$(uname -m)

BUILD_ROOT="$SCRIPT_DIR/appimage-build"
RELEASE_TAR="$BUILD_ROOT/faugus-launcher-$TAG.tar.gz"
RELEASE_SRC_ROOT="$BUILD_ROOT/release-src"
MESON_BUILD_DIR="$BUILD_ROOT/build"
APPDIR="$BUILD_ROOT/AppDir"
QUICK_SHARUN="$BUILD_ROOT/quick-sharun.sh"
OUTPUT="$SCRIPT_DIR/Faugus-$VERSION-$ARCH.AppImage"

for cmd in meson ninja python3 curl tar msgfmt patchelf strace xvfb-run; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Missing required tool: $cmd" >&2
        exit 1
    fi
done

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$RELEASE_SRC_ROOT"

echo "Downloading release $TAG..."
curl -fL -o "$RELEASE_TAR" "$REPO_URL/archive/refs/tags/$TAG.tar.gz"
curl -fL -o "$QUICK_SHARUN" "$QUICK_SHARUN_URL"

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
ninja -C "$MESON_BUILD_DIR" install

PY_DIR=$(python3 -c 'import sysconfig; print(sysconfig.get_path("purelib"))')

export APPDIR
export OUTPATH="$BUILD_ROOT"
export VERSION
export UPINFO="gh-releases-zsync|Faugus|faugus-launcher|latest|*$ARCH.AppImage.zsync"
export APPIMAGE_EXTRACT_AND_RUN=1
export DEPLOY_PYTHON=1
export DEPLOY_GTK=1
export USE_HOST_DRIVERS_EXPERIMENTAL=1
export MAIN_BIN=faugus-launcher
export DESKTOP="/usr/share/applications/$APP_ID.desktop"
export ICON="/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"

xvfb-run -a sh "$QUICK_SHARUN" \
    /usr/bin/faugus-launcher \
    "$PY_DIR/faugus" \
    /usr/lib/girepository-1.0/Adw-1.typelib \
    /usr/lib/girepository-1.0/Manette-0.2.typelib \
    /usr/lib/libadwaita-1.so* \
    /usr/lib/libmanette-0.2.so*

cat > "$APPDIR/bin/faugus-launcher" <<'WRAPPER'
#!/bin/sh
case "$1" in
    --shortcut) shift; exec python3 -m faugus.shortcut "$@";;
    --game)     shift; exec python3 -m faugus.runner --game "$@";;
    --run)      shift; msg="$1"; shift; exec python3 -m faugus.runner "$msg" "$@";;
    --daemon)   shift; exec python3 -m faugus.backup_daemon --daemon;;
    *)          exec python3 -m faugus.launcher "$@";;
esac
WRAPPER
chmod +x "$APPDIR/bin/faugus-launcher"

sh "$QUICK_SHARUN" --make-appimage

rm -f "$OUTPUT"
mv "$BUILD_ROOT"/*.AppImage "$OUTPUT"

echo
echo "Built: $OUTPUT"
