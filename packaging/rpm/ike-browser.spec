# I.K.E. on Fedora: the system's Python, PyQt6 and Qt WebEngine. Built from
# a tarball of the repository (packaging/rpm/README in docs/BUILDING.md):
#   rpmbuild -bb --define "_sourcedir $PWD/dist" packaging/rpm/ike-browser.spec
# The engine module needs Rust 1.88 or later.
%global debug_package %{nil}

Name:           ike-browser
Version:        1.1.1
Release:        1%{?dist}
Summary:        I.K.E. - Internet Kontrol Experience, a private web browser
License:        GPL-3.0-or-later AND MPL-2.0 AND MIT AND ISC AND OFL-1.1
URL:            https://github.com/NullSector-2077/IKE-Browser
Source0:        ike-browser-%{version}.tar.gz
ExclusiveArch:  x86_64

BuildRequires:  gcc
BuildRequires:  cargo >= 1.88
BuildRequires:  rust >= 1.88

Requires:       python3 >= 3.10
Requires:       python3-pyqt6
Requires:       python3-pyqt6-webengine
Requires:       qt6-qtwebengine >= 6.8
Requires:       qt6-qtwebchannel
Requires:       qt6-qtsvg
Requires:       python3-cryptography
Requires:       python3-jeepney
Requires:       hicolor-icon-theme
Recommends:     libnotify
Recommends:     xdg-utils
Suggests:       google-noto-sans-cjk-fonts

%description
A light, independent web browser focused on privacy: no telemetry, no
accounts, no sponsored content, with ad blocking and fingerprinting
protection built in. Pages are rendered by the system's Qt WebEngine; video
and audio formats are the ones this system's engine can decode (I.K.E. ships
no codec of its own; Fedora's build has no H.264 / AAC decoder unless the
system adds one).

%prep
%autosetup -n ike-browser-%{version}

%build
cargo build --release --locked --manifest-path ike-adblock/Cargo.toml --target-dir target
gcc %{optflags} %{build_ldflags} -o ike-browser-launcher launcher/ike-browser.c

%install
sh tools/install-linux.sh %{buildroot} target/release/libike_adblock.so ike-browser-launcher \
    %{_licensedir}/%{name} %{_docdir}/%{name}

%post
python3 -m compileall -q %{_prefix}/lib/ike-browser >/dev/null 2>&1 || :

%preun
find %{_prefix}/lib/ike-browser -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || :

%files
%{_bindir}/ike-browser
%{_prefix}/lib/ike-browser/
%{_datadir}/applications/ike-browser.desktop
%{_datadir}/icons/hicolor/*/apps/ike-browser.*
%{_datadir}/pixmaps/ike-browser.png
%license %{_licensedir}/%{name}/
%doc %{_docdir}/%{name}/

%changelog
* Mon Nov 16 2026 The I.K.E. project <noreply@github.com> - 1.1.1-1
- See CHANGELOG.md in the documentation folder.
