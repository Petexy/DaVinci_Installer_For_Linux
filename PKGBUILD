# Maintainer: Petexy <https://github.com/Petexy>

pkgname=davinci-installer
pkgver=2.0.1.r
pkgrel=2
_currentdate=$(date +"%Y-%m-%d%H-%M-%S")
pkgdesc='Smart Installer for Affinity suite for Linux'
url='https://github.com/Petexy'
arch=(x86_64)
license=('GPL-3.0')
depends=(
  python-gobject
  gtk4
  libadwaita
  python
  pipewire-pulse
  pulseaudio-alsa
  linexin-center
)
makedepends=(
)
install="${pkgname}.install"

package() {
   mkdir -p ${pkgdir}/usr/share/applications
   mkdir -p ${pkgdir}/usr/share/linexin
   mkdir -p ${pkgdir}/usr/share/icons
   cp -rf ${srcdir}/usr ${pkgdir}/
}
