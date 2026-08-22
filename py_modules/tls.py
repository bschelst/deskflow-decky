# Schelstraete Bart - bart@schelstraete.org - https://github.com/bschelst/deskflow-decky

"""TLS certificate and trust handling.

``deskflow-core`` cannot generate its own certificate -- generation lives in Deskflow's
GUI library, which the engine binary does not link (upstream issue #8913, reported from
a Steam Deck). So the plugin generates it.

Trust is TOFU fingerprint pinning. Deskflow reads a flat list from
``tls/trusted-servers`` with no host association, which cannot distinguish "a new
server" from "this server's key changed". The second case is a possible interception
and must look different to the user, so the plugin keeps its own host -> fingerprint
map alongside.
"""

import json
import os
import re
import string
import tempfile

__all__ = [
    "PinnedHosts",
    "TrustStore",
    "certificate_fingerprint",
    "ensure_certificate",
    "format_fingerprint",
    "normalise_fingerprint",
    "write_private",
]

SHA256_HEX_LENGTH = 64
_HEX = frozenset(string.hexdigits.lower())
_V2_LINE = re.compile(r"^v2:sha256:([0-9a-fA-F]{64})\Z")


def normalise_fingerprint(value):
    """Accept the forms a fingerprint arrives in and return bare lowercase hex."""
    if not isinstance(value, str):
        raise ValueError("fingerprint must be text")
    text = value.strip()
    if text.lower().startswith("v2:sha256:"):
        text = text[len("v2:sha256:") :]
    text = text.replace(":", "").replace(" ", "").lower()
    if len(text) != SHA256_HEX_LENGTH or any(ch not in _HEX for ch in text):
        raise ValueError("not a SHA-256 fingerprint")
    return text


def format_fingerprint(value):
    """Group into byte pairs so a human can compare it against the server's display."""
    hexed = normalise_fingerprint(value).upper()
    return ":".join(hexed[i : i + 2] for i in range(0, len(hexed), 2))


def write_private(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    handle, temp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


class TrustStore:
    """Deskflow's ``trusted-servers`` file, in its own ``v2:sha256:<hex>`` format."""

    def __init__(self, path):
        self.path = path

    def all(self):
        try:
            with open(self.path, encoding="utf-8") as stream:
                raw = stream.read()
        except OSError:
            return []
        except UnicodeDecodeError:
            # A binary or corrupted file is treated as "trusts nothing", never as a
            # reason to crash startup.
            return []

        found = []
        for line in raw.splitlines():
            match = _V2_LINE.match(line.strip())
            if match:
                fingerprint = match.group(1).lower()
                if fingerprint not in found:
                    found.append(fingerprint)
        return found

    def is_trusted(self, fingerprint):
        try:
            target = normalise_fingerprint(fingerprint)
        except ValueError:
            return False
        return target in self.all()

    def add(self, fingerprint):
        target = normalise_fingerprint(fingerprint)
        current = self.all()
        if target in current:
            return
        current.append(target)
        self._save(current)

    def remove(self, fingerprint):
        target = normalise_fingerprint(fingerprint)
        self._save([fp for fp in self.all() if fp != target])

    def _save(self, fingerprints):
        text = "".join(f"v2:sha256:{fp}\n" for fp in fingerprints)
        write_private(self.path, text)


class PinnedHosts:
    """host -> fingerprint, so a *changed* key can be told apart from a new one."""

    def __init__(self, path):
        self.path = path

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError, UnicodeDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            host: fp
            for host, fp in data.items()
            if isinstance(host, str) and isinstance(fp, str) and len(fp) == SHA256_HEX_LENGTH
        }

    def get(self, host):
        return self._load().get(host)

    def classify(self, host, fingerprint):
        """Return 'trusted', 'changed', or 'unknown' for this host's fingerprint."""
        try:
            target = normalise_fingerprint(fingerprint)
        except ValueError:
            return "unknown"
        known = self._load().get(host)
        if known is None:
            return "unknown"
        return "trusted" if known == target else "changed"

    def pin(self, host, fingerprint):
        target = normalise_fingerprint(fingerprint)
        data = self._load()
        data[host] = target
        write_private(self.path, json.dumps(data, indent=2, sort_keys=True))

    def unpin(self, host):
        data = self._load()
        if data.pop(host, None) is not None:
            write_private(self.path, json.dumps(data, indent=2, sort_keys=True))


def certificate_arguments(cert_path, common_name):
    """The openssl argument list used to create the Deck's certificate.

    Kept separate from execution so the command can be asserted in tests without
    running anything, and so it is obvious there is no shell involved.
    """
    return [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-sha256",
        "-days",
        "3650",
        "-nodes",
        "-keyout",
        cert_path,
        "-out",
        cert_path,
        "-subj",
        f"/CN={common_name}",
    ]


async def ensure_certificate(cert_path, common_name, runner):
    """Create the certificate if it is missing. Returns True if one was generated.

    Regenerating changes the Deck's fingerprint and forces re-pairing on the peer, so
    an existing certificate is always left alone.

    Generation goes into a 0600 temporary file and is then renamed into place. Letting
    openssl write the final path directly would create the private key under the
    process umask and only tighten it afterwards -- a window during RSA key generation
    in which the key is readable by anyone who can reach the directory.
    """
    if os.path.exists(cert_path) and os.path.getsize(cert_path) > 0:
        return False

    directory = os.path.dirname(os.path.abspath(cert_path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    # makedirs with exist_ok does not tighten a directory that already existed, and a
    # loose one would undo the protection above.
    os.chmod(directory, 0o700)

    handle, temp_path = tempfile.mkstemp(dir=directory, prefix=".cert-")
    os.close(handle)
    try:
        os.chmod(temp_path, 0o600)
        await runner(certificate_arguments(temp_path, common_name))
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            raise RuntimeError("certificate generation did not produce a file")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, cert_path)
    except BaseException:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    return True


async def certificate_fingerprint(cert_path, runner):
    """SHA-256 fingerprint of our own certificate, for display to the user."""
    output = await runner(
        ["openssl", "x509", "-in", cert_path, "-noout", "-fingerprint", "-sha256"]
    )
    text = output.decode("utf-8", "replace") if isinstance(output, bytes) else str(output)
    _, _, tail = text.partition("=")
    return normalise_fingerprint(tail)
