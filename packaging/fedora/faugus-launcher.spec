Name:           faugus-launcher
Version:        2.0.1
Release:        1%{?dist}
Summary:        A simple and lightweight app for running Windows games using UMU-Launcher

License:        MIT
URL:            https://github.com/Faugus/faugus-launcher
Source0:        https://github.com/Faugus/faugus-launcher/archive/refs/tags/%{version}.tar.gz#/%{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  meson gtk-update-icon-cache python3-devel
Requires:       python3-gobject python3-requests python3-pillow python3-vdf python3-psutil python3-dbus gtk4 libadwaita libmanette python3-icoextract

%description
A simple and lightweight app for running Windows games using UMU-Launcher/UMU-Proton.

%prep
%autosetup -n %{name}-%{version}

%build
%meson
%meson_build

%install
%meson_install

%files
%license LICENSE
%{_bindir}/faugus-launcher
%{python3_sitelib}/faugus/
%{_datadir}/applications/*.desktop
%{_datadir}/icons/hicolor/scalable/actions/*.svg
%{_datadir}/icons/hicolor/scalable/apps/*.svg
%{_datadir}/faugus-launcher/*
%{_datadir}/locale/*/LC_MESSAGES/*.mo
%{_datadir}/metainfo/io.github.Faugus.faugus-launcher.metainfo.xml
