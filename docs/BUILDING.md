# Building I.K.E. Browser

The only current packaging target is Arch Linux / CachyOS x86_64. Follow the detailed [Arch build instructions](arch/BUILDING.md).

The package uses system-provided Python, PyQt6, Qt WebEngine and Qt modules; it does not bundle a separate Python or Qt runtime. Build with `makepkg -si` after installing the required build tools.

Windows and AppImage build systems are not included in this repository's current scope.
