pkgname=faugus-launcher
pkgver=1.0
pkgrel=17
pkgdesc="Simple and Lightweight Game Launcher"
arch=('x86_64')
license=('GPL')
depends=('python' 'python-gobject' 'umu-launcher' 'p7zip')
provides=('faugus-launcher')
conflicts=('faugus-launcher')

source=("${pkgname}::git+https://github.com/Faugus/faugus-launcher.git")
sha256sums=('SKIP')

package() {
    cd "$srcdir/${pkgname}"
    install -Dm755 faugus-launcher.py "$pkgdir/usr/bin/faugus-launcher"
    install -Dm644 faugus-launcher.desktop "$pkgdir/usr/share/applications/faugus-launcher.desktop"
    install -Dm644 faugus-launcher.png "$pkgdir/usr/share/icons/faugus-launcher.png"
}
