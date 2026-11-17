#!/bin/sh
# Standalone fixed-release entry: safe from a pipe or saved file in any cwd.
set -eu
umask 077
version=0.2.8-mvp-dev
repository=lajidonggua/AgRelay-releases
installer_sha256=00c28aecff1774010239dff0c7a6e0c60113068e072d53f11fc4eed96700b010

case "${1:-}" in
  -h|--help)
    printf '%s\n' 'AgRelay quick installer: Apple Silicon Mac, existing Python3.9+.' \
      'Installs verified 0.2.8 binaries in ~/.agrelay-app and ~/.local/bin.' \
      'Optional installer arguments: --prefix /absolute/new/path --bin-dir /absolute/user/bin.' \
      'Existing files are preserved. Setup, SSH and model calls are not automatic.'
    exit 0 ;;
esac
if [ "$(/usr/bin/uname -s)" != Darwin ] || [ "$(/usr/bin/uname -m)" != arm64 ]; then
  printf 'AgRelay requires Apple Silicon macOS.\n' >&2
  exit 3
fi
if ! command -v python3 >/dev/null 2>&1 || ! python3 -I -S -B -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)'; then
  printf 'Install an existing Python3.9+ first. No dependency was installed.\n' >&2
  exit 3
fi
work=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/agrelay-quick.XXXXXX")
trap '/bin/rm -rf "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
base="https://github.com/$repository/releases/download/v$version"
fetch() {
  if ! /usr/bin/curl --fail --silent --show-error --location \
    --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 180 \
    --max-filesize "$3" "$base/$1" -o "$2"; then
    printf 'AgRelay download failed; no installed files were changed.\n' >&2
    exit 3
  fi
}
fetch install.py "$work/install.py" 131072
python3 -I -S -B -c 'import hashlib,pathlib,sys
if hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest()!=sys.argv[2]:
 sys.exit("AgRelay installer checksum mismatch; nothing installed.")' "$work/install.py" "$installer_sha256"
archive="agrelay-$version-darwin-arm64.tar.gz"
fetch "$archive.sha256" "$work/$archive.sha256" 1024
fetch "$archive" "$work/$archive" 134217728
launcher_dir=$(python3 -I -S -B -c 'import pathlib; print(pathlib.Path.home().resolve()/".local"/"bin")')
python3 -I -S -B "$work/install.py" --archive "$work/$archive" \
  --sha256 "$work/$archive.sha256" --bin-dir "$launcher_dir" "$@"
