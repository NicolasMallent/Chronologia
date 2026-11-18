#!/usr/bin/env bash
# Construit le paquet .deb à partir du dossier PyInstaller.
# Usage : packaging/deb/build_deb.sh <version> [dossier_pyinstaller] [dossier_sortie]
set -euo pipefail

VERSION="${1:?version manquante (ex. 0.1.0)}"
BUNDLE="${2:-dist/chronologia}"
OUT="${3:-dist}"
[[ "$VERSION" =~ ^[0-9]+(\.[0-9]+)*([.+~-][0-9A-Za-z.]+)?$ ]] || { echo "version invalide : $VERSION" >&2; exit 1; }
[ -x "$BUNDLE/chronologia" ] || { echo "bundle introuvable : $BUNDLE" >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PKG="$STAGE/chronologia_${VERSION}_amd64"

install -d "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" \
    "$PKG/usr/share/icons/hicolor/256x256/apps" "$PKG/usr/share/doc/chronologia"
cp -a "$BUNDLE" "$PKG/opt/chronologia"
ln -s /opt/chronologia/chronologia "$PKG/usr/bin/chronologia"
install -m 0644 "$ROOT/packaging/deb/chronologia.desktop" "$PKG/usr/share/applications/chronologia.desktop"
install -m 0644 "$ROOT/packaging/icon.png" "$PKG/usr/share/icons/hicolor/256x256/apps/chronologia.png"
install -m 0644 "$ROOT/LICENSE" "$PKG/usr/share/doc/chronologia/copyright"
install -m 0644 "$ROOT/packaging/THIRD-PARTY-NOTICES.md" "$PKG/usr/share/doc/chronologia/THIRD-PARTY-NOTICES.md"

# droits : racine propriétaire, personne d'autre n'écrit
find "$PKG" -type d -exec chmod 0755 {} +
find "$PKG/opt" -type f ! -perm /111 -exec chmod 0644 {} +
find "$PKG/opt" -type f -perm /111 -exec chmod 0755 {} +

SIZE_KB="$(du -sk --exclude=DEBIAN "$PKG" | cut -f1)"
cat > "$PKG/DEBIAN/control" <<CONTROL
Package: chronologia
Version: ${VERSION}
Section: graphics
Priority: optional
Architecture: amd64
Installed-Size: ${SIZE_KB}
Maintainer: Chronologia <noreply@github.com>
Depends: libc6 (>= 2.35), libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxcb-xkb1, libxkbcommon-x11-0, libegl1, libgl1, libfontconfig1, libdbus-1-3, libglib2.0-0
Description: Printable timelines from a CSV file
 Chronologia displays periods and events from a CSV file on a timeline,
 lets you edit them, and exports a vector PDF for large-format printing.
 All data stays on your computer: the application makes no network access.
CONTROL

mkdir -p "$OUT"
DEB="$OUT/chronologia_${VERSION}_amd64.deb"
dpkg-deb --build --root-owner-group -Zxz "$PKG" "$DEB"
echo "$DEB"
