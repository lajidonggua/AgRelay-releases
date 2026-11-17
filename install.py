#!/usr/bin/env python3
"""Exclusive private install; uninstall removes only intact owned artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import shlex
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

FILES = ("agrelay", "agrelay-approval")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+-mvp-dev")
REPOSITORY = "lajidonggua/AgRelay"
MAX_ARCHIVE = 128 * 1024 * 1024


def safe_version(value):
    if not VERSION.fullmatch(value):
        raise RuntimeError("invalid release version")
    return value


def asset_name(version):
    return "agrelay-" + safe_version(version) + "-darwin-arm64.tar.gz"


def owned_directory(path, private=False):
    s = path.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o022 or (private and stat.S_IMODE(s.st_mode) != 0o700):
        raise RuntimeError("unsafe installation directory")


def user_directory(path):
    # Create missing user-owned parents; never chmod an existing directory.
    if not path.is_absolute():
        raise RuntimeError("absolute installation directory required")
    if not path.exists() and not path.is_symlink():
        user_directory(path.parent)
        path.mkdir(mode=0o700)
    owned_directory(path)


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_download_url(url):
    value = urllib.parse.urlsplit(url)
    host = value.hostname or ""
    if value.scheme != "https" or value.username or value.password or value.port not in (None, 443) or not (host == "github.com" or host.endswith(".githubusercontent.com")):
        raise RuntimeError("release redirect outside HTTPS GitHub assets refused")


def fetch(url, destination, limit):
    check_download_url(url)
    opener = urllib.request.build_opener(HTTPSRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "AgRelay-installer", "Accept-Encoding": "identity"})
    deadline = time.monotonic() + 120
    try:
        with opener.open(request, timeout=20) as response, destination.open("xb") as output:
            check_download_url(response.geturl())
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                total += len(chunk)
                if total > limit or time.monotonic() > deadline:
                    raise RuntimeError("release download budget exceeded")
                if not chunk:
                    break
                output.write(chunk)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 404):
            raise RuntimeError("release unavailable or private; download archive and checksum from an authenticated GitHub browser, then use --archive and --sha256") from None
        raise RuntimeError("release download failed") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("release download failed; check the network and retry installation") from None


def archive_source(archive, checksum, destination):
    if archive.stat().st_size > MAX_ARCHIVE or checksum.stat().st_size > 1024:
        raise RuntimeError("release archive budget exceeded")
    match = re.fullmatch(r"([0-9a-f]{64})  ([a-zA-Z0-9_.-]+)\n?", checksum.read_text())
    if not match or match[2] != archive.name or digest(archive) != match[1]:
        raise RuntimeError("release SHA-256 verification failed; nothing installed")
    version = archive.name.removeprefix("agrelay-").removesuffix("-darwin-arm64.tar.gz")
    if asset_name(version) != archive.name:
        raise RuntimeError("unsupported release archive name")
    top = archive.name.removesuffix(".tar.gz")
    with tarfile.open(archive, "r:gz") as tar:
        members = {}
        total = 0
        for entry in tar:
            parts = entry.name.split("/")
            if len(members) >= 512 or parts[0] != top or any(x in ("", ".", "..") for x in parts) or entry.name in members or not (entry.isdir() or entry.isfile()) or entry.size > MAX_ARCHIVE or entry.size < 0:
                raise RuntimeError("unsafe release archive")
            total += entry.size
            if total > 2 * MAX_ARCHIVE:
                raise RuntimeError("release contents budget exceeded")
            members[entry.name] = entry
        metadata = members.get(top + "/SHA256.json")
        if not metadata or not metadata.isfile() or metadata.size > 128 * 1024:
            raise RuntimeError("release manifest missing or too large")
        manifest = json.load(tar.extractfile(metadata))
        regular = {key.removeprefix(top + "/") for key, value in members.items() if value.isfile() and key != metadata.name}
        if not isinstance(manifest, dict) or set(manifest) != regular or not all("bin/" + name in manifest for name in FILES):
            raise RuntimeError("release manifest contents mismatch")
        for name, expected in manifest.items():
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise RuntimeError("invalid release manifest")
            with tar.extractfile(members[top + "/" + name]) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()
            if actual != expected:
                raise RuntimeError("release file hash mismatch")
        destination.mkdir(mode=0o700)
        # Never extract paths from the archive. Only copy these two exact files.
        for name in FILES:
            with tar.extractfile(members[top + "/bin/" + name]) as src, (destination / name).open("xb") as dst:
                shutil.copyfileobj(src, dst)
            (destination / name).chmod(0o700)
    return version


def uninstall(prefix):
    owned(prefix, True)
    expected = set(FILES) | {"agrelay-install.json"}
    if {v.name for v in prefix.iterdir()} != expected:
        raise RuntimeError("unknown files: preserve installation for manual inspection")
    for name in expected:
        owned(prefix / name)
    if (prefix / "agrelay-install.json").stat().st_size > 16 * 1024:
        raise RuntimeError("ownership manifest exceeds budget")
    manifest = json.loads((prefix / "agrelay-install.json").read_text())
    if manifest.get("owner") != "AgRelay MVP" or set(manifest.get("sha256", {})) != set(FILES):
        raise RuntimeError("ownership manifest mismatch")
    for name in FILES:
        if digest(prefix / name) != manifest["sha256"][name]:
            raise RuntimeError("modified binary: preserve installation for manual inspection")
    launcher = manifest.get("launcher")
    if launcher:
        path = Path(launcher["path"])
        if not path.is_absolute() or path.name != "agrelay":
            raise RuntimeError("invalid launcher ownership record")
        owned_directory(path.parent)
        owned(path)
        script = "#!/bin/sh\nexec " + shlex.quote(str(prefix / "agrelay")) + ' "$@"\n'
        if digest(path) != launcher["sha256"] or launcher["sha256"] != hashlib.sha256(script.encode()).hexdigest():
            raise RuntimeError("modified launcher: preserve installation for manual inspection")
        path.unlink()
    for name in expected:
        (prefix / name).unlink()
    prefix.rmdir()
    print("Uninstalled owned binaries and launcher. Projects, state, SSH settings and native history retained.")


def install(source, prefix, bin_dir, version):
    if not prefix.is_absolute() or prefix.parent.resolve() / prefix.name != prefix or prefix.name in ("", ".", ".."):
        raise RuntimeError("absolute canonical prefix with existing parent required")
    owned_directory(prefix.parent)
    launcher = None
    if bin_dir:
        user_directory(bin_dir)
        if bin_dir.resolve() != bin_dir or bin_dir == prefix or prefix in bin_dir.parents:
            raise RuntimeError("launcher directory must be canonical and separate from installation")
        launcher = bin_dir / "agrelay"
        if os.path.lexists(launcher):
            raise RuntimeError("agrelay launcher already exists; existing command preserved. Install without --bin-dir or explicitly uninstall the owned older version first")
    for name in FILES:
        s = (source / name).lstat()
        if not stat.S_ISREG(s.st_mode) or not os.access(source / name, os.X_OK):
            raise RuntimeError("missing built artifact")
    prefix.mkdir(mode=0o700)
    created = []
    launcher_created = False
    try:
        hashes = {}
        for name in FILES:
            with (source / name).open("rb") as src, (prefix / name).open("xb") as dst:
                created.append(name)
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
            (prefix / name).chmod(0o700)
            hashes[name] = digest(prefix / name)
        manifest = {"owner": "AgRelay MVP", "version": version, "sha256": hashes}
        if launcher:
            script = "#!/bin/sh\nexec " + shlex.quote(str(prefix / "agrelay")) + ' "$@"\n'
            with launcher.open("x") as stream:
                launcher_created = True
                stream.write(script);stream.flush();os.fsync(stream.fileno())
            launcher.chmod(0o700)
            manifest["launcher"] = {"path": str(launcher), "sha256": digest(launcher)}
        with (prefix / "agrelay-install.json").open("x") as stream:
            created.append("agrelay-install.json")
            json.dump(manifest, stream, indent=2)
            stream.flush();os.fsync(stream.fileno())
    except BaseException:
        if launcher_created:
            launcher.unlink()
        for name in created:
            (prefix / name).unlink()
        prefix.rmdir()
        raise
    print("Installed", version, "at", prefix)
    if bin_dir:
        print("For this Terminal, run: export PATH=" + shlex.quote(str(bin_dir)) + ':"$PATH"')
    print("Next:", shlex.quote(str(launcher or prefix / "agrelay")), "setup")
    print("No shell profiles, system settings, SSH configuration or model credentials changed.")
    print("To uninstall, rerun this installer with --prefix", shlex.quote(str(prefix)), "--uninstall")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()


def owned(path, directory=False):
    s = path.lstat()
    if s.st_uid != os.getuid() or (not directory and s.st_nlink != 1) or (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)) is not True or stat.S_IMODE(s.st_mode) != (0o700 if directory or path.name in FILES else 0o600):
        raise RuntimeError("unsafe owned artifact")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, help="absolute private NEW directory; default ~/.agrelay-app/VERSION")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--source", type=Path, help="existing locally built binary directory")
    source.add_argument("--archive", type=Path, help="downloaded release archive (also requires --sha256)")
    source.add_argument("--download", metavar="VERSION", help="download a fixed GitHub release using HTTPS, no credentials")
    parser.add_argument("--sha256", type=Path, help="release .sha256 file")
    parser.add_argument("--bin-dir", type=Path, help="optional user-owned launcher directory; refuses command conflicts")
    parser.add_argument("--uninstall", action="store_true")
    a = parser.parse_args()
    os.umask(0o077)
    if a.uninstall:
        if not a.prefix or a.source or a.archive or a.download or a.sha256 or a.bin_dir:
            raise RuntimeError("uninstall requires only --prefix and --uninstall")
        if not a.prefix.is_absolute() or a.prefix.parent.resolve() / a.prefix.name != a.prefix:
            raise RuntimeError("absolute canonical prefix required")
        uninstall(a.prefix)
        return
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("installation supports Apple Silicon macOS only")
    if bool(a.archive) != bool(a.sha256):
        raise RuntimeError("--archive and --sha256 must be used together")
    with tempfile.TemporaryDirectory(prefix="agrelay-install-") as scratch:
        tmp = Path(scratch)
        binary_source = a.source or Path(__file__).resolve().parent.parent / "bin"
        if a.download:
            version = safe_version(a.download)
            filename = asset_name(version)
            base = "https://github.com/" + REPOSITORY + "/releases/download/v" + version + "/"
            a.archive, a.sha256 = tmp / filename, tmp / (filename + ".sha256")
            fetch(base + filename + ".sha256", a.sha256, 1024)
            fetch(base + filename, a.archive, MAX_ARCHIVE)
        if a.archive:
            version = archive_source(a.archive, a.sha256, tmp / "binaries")
            binary_source = tmp / "binaries"
        bundled = binary_source.parent / "SHA256.json"
        if bundled.exists():
            if bundled.stat().st_size > 128 * 1024:
                raise RuntimeError("release manifest exceeds budget")
            manifest = json.loads(bundled.read_text())
            if any(manifest.get("bin/" + name) != digest(binary_source / name) for name in FILES):
                raise RuntimeError("bundled binary hash mismatch")
        result = subprocess.run([str(binary_source / "agrelay"), "--version"], check=True, capture_output=True, text=True, timeout=10)
        match = re.fullmatch(r"agrelay (" + VERSION.pattern + r")\n", result.stdout)
        if not match or (a.archive and match[1] != version):
            raise RuntimeError("binary release version mismatch")
        version = match[1]
        prefix = a.prefix
        if prefix is None:
            parent = Path.home().resolve() / ".agrelay-app"
            if not parent.exists() and not parent.is_symlink():
                parent.mkdir(mode=0o700)
            owned_directory(parent, private=True)
            prefix = parent / version
        install(binary_source, prefix, a.bin_dir, version)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as error:
        # Never print remote bodies, credentials, argv or Python tracebacks.
        print("AgRelay installation failed:", str(error) if isinstance(error, RuntimeError) else "invalid or unavailable installation input", file=sys.stderr)
        raise SystemExit(3)
