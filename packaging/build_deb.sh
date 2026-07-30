#!/usr/bin/env bash
# Empaqueta dist/MeetTranscriptions (salida onedir de PyInstaller) como .deb.
#
# Requisitos previos:
#   pip install ".[gui]" pyinstaller
#   pyinstaller packaging/transcriptor.spec
# Luego:
#   bash packaging/build_deb.sh
# Genera: dist/meet-transcriptions_<version>_amd64.deb
#
# El bundle es autocontenido (Python + Qt adentro, en /opt): no depende de
# la versión de Python del sistema. ffmpeg va como Recommends: apt lo
# instala por defecto, y si falta la app ofrece descargarlo.

set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(python3 -c "import sys; sys.path.insert(0, '.'); from transcriptor import __version__; print(__version__)")
ARCH=amd64
PKG=meet-transcriptions
ROOT="build/deb/${PKG}_${VERSION}_${ARCH}"

test -d dist/MeetTranscriptions || { echo "Falta dist/MeetTranscriptions: corré pyinstaller primero"; exit 1; }

rm -rf "$ROOT"
mkdir -p "$ROOT/DEBIAN" \
         "$ROOT/opt/meet-transcriptions" \
         "$ROOT/usr/bin" \
         "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/icons/hicolor/256x256/apps" \
         "$ROOT/usr/share/doc/$PKG"

cp -a dist/MeetTranscriptions/. "$ROOT/opt/meet-transcriptions/"
ln -s /opt/meet-transcriptions/MeetTranscriptions "$ROOT/usr/bin/meet-transcriptions"
cp packaging/linux/meet-transcriptions.desktop "$ROOT/usr/share/applications/"
python3 packaging/make_png_icon.py "$ROOT/usr/share/icons/hicolor/256x256/apps/meet-transcriptions.png"
cp LICENSE "$ROOT/usr/share/doc/$PKG/copyright"

SIZE=$(du -sk "$ROOT" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Architecture: $ARCH
Maintainer: TRANS-IT Foundation <dax@trans-it-foundation.org>
Installed-Size: $SIZE
Depends: libc6 (>= 2.31), libxcb1
Recommends: ffmpeg
Section: sound
Priority: optional
Homepage: https://github.com/daxcoletti/meet-transcriptions
Description: Automatic meeting transcription with AI minutes
 Watches a recordings folder and generates speaker-diarized transcripts
 (VTT, TXT, JSON) plus AI-written meeting minutes in Markdown, rotating
 across the free tiers of several transcription APIs. Lives in the
 system tray; includes a first-run setup wizard. Bilingual (en/es).
EOF

dpkg-deb --build --root-owner-group "$ROOT" "dist/${PKG}_${VERSION}_${ARCH}.deb"
echo "OK -> dist/${PKG}_${VERSION}_${ARCH}.deb"
