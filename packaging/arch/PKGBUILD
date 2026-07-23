# Maintainer: Faugus <felix.ribeiro@live.com>

pkgname=faugus-launcher
pkgver=2.0.1
pkgrel=1
pkgdesc="A simple and lightweight app for running Windows games using UMU-Launcher"
arch=('any')
url="https://github.com/Faugus/faugus-launcher"
license=('MIT')
depends=('python-gobject' 'python-requests' 'python-pillow' 'python-vdf' 'python-psutil' 'python-dbus' 'icoextract' 'gtk4' 'libadwaita' 'libmanette')
makedepends=('meson')
provides=('faugus-launcher')
conflicts=('faugus-launcher')
source=("https://github.com/Faugus/${pkgname}/archive/refs/tags/${pkgver}.tar.gz")
sha256sums=('SKIP')

build() {
    cd "${pkgname}-${pkgver}"
    arch-meson . build
    meson compile -C build
}

package() {
    cd "${pkgname}-${pkgver}"
    DESTDIR="${pkgdir}" meson install -C build
}
