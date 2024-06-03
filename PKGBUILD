pkgname=faugus-launcher
pkgver=1.0
pkgrel=17
pkgdesc="Simple and Lightweight Game Launcher"
arch=('x86_64')
license=('GPL')
depends=('python' 'python-gobject' 'umu-launcher' 'p7zip')
provides=('faugus-launcher')
conflicts=('faugus-launcher')

source=("${pkgname}::git+https://github.com/Faugus/faugus-launcher.git"
	"faugus-launcher.py"
	"faugus-launcher.desktop"
	"faugus-launcher.png")
sha256sums=('b0f057fbf793feea15345f4f69cc8c4222ccdf7e7ff705bf97c1325304eeaf1a'
            '7ee643017060562d27ad3f0960911bf7e5299df8d526863dd428f84a4765aa67'
            '36ca089b98e4169f17572dde833bd1039f8f5484a40ca307e6871de3814ea159')

package() {
    install -Dm755 faugus-launcher.py "$pkgdir/usr/bin/faugus-launcher"
    install -Dm644 faugus-launcher.desktop "$pkgdir/usr/share/applications/faugus-launcher.desktop"
    install -Dm644 faugus-launcher.png "$pkgdir/usr/share/icons/faugus-launcher.png"
}
