"""Bounded, origin-allowlisted acquisition transport; no proxy environment support."""

import hashlib
import http.client
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlsplit
from zipfile import ZipFile


class PolicyError(ValueError):
    """An outbound operation needs operator policy review."""


class TransportError(ValueError):
    def __init__(self, status, retry_after=None):
        super().__init__(f"source_http_{status}")
        self.status = status
        self.retry_after = retry_after


def approved_url(url, origins):
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not host
            or parsed.fragment
            or host != host.encode("idna").decode("ascii")
            or "\\" in url
            or any(ord(char) < 33 for char in url)
        ):
            raise ValueError
        origin = f"https://{host}"
        if origin not in origins:
            raise ValueError
        # Literal addresses are never approved source origins.
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError
        if host.endswith(".") or host.isdigit():
            raise ValueError
    except (ValueError, UnicodeError):
        raise PolicyError("network_policy_review_required") from None
    return parsed


def public_addresses(host, resolver=None):
    resolver = resolver or socket.getaddrinfo
    addresses = []
    for family, socktype, protocol, _, address in resolver(host, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(address[0]).is_global:
            raise PolicyError("non_public_source_address")
        addresses.append((family, socktype, protocol, address))
    if not addresses:
        raise PolicyError("source_dns_empty")
    return addresses


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, addresses, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.addresses = addresses

    def connect(self):
        # Connect to a validated address directly. TLS still verifies the origin hostname;
        # neither a second DNS lookup nor HTTPS_PROXY can change the destination.
        last_error = None
        for family, socktype, protocol, address in self.addresses:
            sock = socket.socket(family, socktype, protocol)
            sock.settimeout(self.timeout)
            try:
                sock.connect(address)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as error:
                sock.close()
                last_error = error
        raise OSError("source_connection_failed") from last_error


class BoundedResponse:
    def __init__(self, response, connection, max_bytes, max_seconds):
        self.response, self.connection = response, connection
        self.headers, self.status = response.headers, response.status
        self.max_bytes, self.max_seconds = max_bytes, max_seconds
        self.received, self.started = 0, time.monotonic()
        self.account = lambda _count: None
        length = self.headers.get("Content-Length")
        self.expected = int(length) if length else None
        if self.expected is not None and self.expected > max_bytes:
            self.close()
            raise PolicyError("artifact_byte_limit")

    def read(self, size=-1):
        if time.monotonic() - self.started > self.max_seconds:
            raise PolicyError("artifact_time_limit")
        remaining = self.max_bytes - self.received
        size = min(size if size >= 0 else remaining + 1, remaining + 1)
        self.account(0)
        chunk = self.response.read(size)
        self.received += len(chunk)
        self.account(len(chunk))
        if time.monotonic() - self.started > self.max_seconds:
            raise PolicyError("artifact_time_limit")
        if self.received > self.max_bytes:
            raise PolicyError("artifact_byte_limit")
        if not chunk and self.expected is not None and self.received != self.expected:
            raise OSError("incomplete_artifact")
        return chunk

    def close(self):
        self.response.close()
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Transport:
    def __init__(self, policy, *, connector=None, resolver=None):
        self.policy = policy
        self.connector = connector or _PinnedHTTPS
        self.resolver = resolver or socket.getaddrinfo
        self.requests = 0
        self.bytes = 0

    def _account(self, count):
        self.policy.get("_check", lambda: None)()
        self.bytes += count
        ceiling = self.policy.get("max_artifact_bytes", 20 * 1024**3)
        if self.bytes > self.policy.get("max_total_bytes", ceiling * 2):
            raise PolicyError("source_byte_budget_exhausted")

    def get(self, url, headers=None):
        self.policy.get("_check", lambda: None)()
        if self.policy.get("mode", "offline") != "bulk_only":
            raise PolicyError("source_network_disabled")
        if self.policy.get("can_fetch", True) not in (True, "allow"):
            raise PolicyError("source_fetch_denied")
        request_headers = {"User-Agent": "bord-food-api/1.0", "Accept-Encoding": "identity"}
        request_headers.update(headers or {})
        origins = self.policy.get("origins", [])
        for _ in range(self.policy.get("max_redirects", 3) + 1):
            self.policy.get("_check", lambda: None)()
            parsed = approved_url(url, origins)
            if self.requests >= self.policy.get("max_requests", 100):
                raise PolicyError("request_budget_exhausted")
            addresses = public_addresses(parsed.hostname, self.resolver)
            connection = self.connector(parsed.hostname, addresses, self.policy.get("timeout", 30))
            self.requests += 1
            try:
                connection.request(
                    "GET",
                    parsed.path + ("?" + parsed.query if parsed.query else ""),
                    headers=request_headers,
                )
                response = connection.getresponse()
            except Exception:
                connection.close()
                raise
            if response.status in (301, 302, 303, 307, 308):
                target = urljoin(url, response.headers.get("Location", ""))
                response.close()
                connection.close()
                target_parsed = approved_url(target, origins)
                if target_parsed.hostname != parsed.hostname:
                    request_headers = {
                        key: value
                        for key, value in request_headers.items()
                        if key.lower() not in ("authorization", "cookie", "x-api-key")
                    }
                url = target
                continue
            if response.status not in (200, 206, 304):
                status = response.status
                retry_after = response.headers.get("Retry-After")
                response.close()
                connection.close()
                raise TransportError(status, retry_after)
            bounded = BoundedResponse(
                response,
                connection,
                self.policy.get("max_artifact_bytes", 20 * 1024**3),
                self.policy.get("max_seconds", 3600),
            )
            bounded.url = url
            bounded.account = self._account
            return bounded
        raise PolicyError("redirect_limit")

    def fetch(self, url, destination, *, validators=None):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        ceiling = self.policy.get("max_artifact_bytes", 20 * 1024**3)
        reserve = self.policy.get("free_space_reserve_bytes", 0)
        temporary = destination.with_name(destination.name + ".part")
        state_path = destination.with_name(destination.name + ".part.json")
        resume = None
        if temporary.exists() and state_path.exists():
            try:
                candidate = json.loads(state_path.read_text())
                if (
                    candidate.get("url") == url
                    and candidate.get("etag")
                    and not candidate["etag"].startswith("W/")
                    and temporary.stat().st_size <= candidate["total"] <= ceiling
                ):
                    resume = candidate
            except (ValueError, KeyError, TypeError):
                pass
        if resume is None:
            temporary.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
        if self.policy.get("data_root") and self.policy.get("data_quota_bytes"):
            used = sum(
                path.stat().st_size
                for path in Path(self.policy["data_root"]).rglob("*")
                if path.is_file() and not path.is_symlink()
            )
            if used + ceiling > self.policy["data_quota_bytes"]:
                raise PolicyError("installation_quota_exhausted")
        offset = temporary.stat().st_size if resume else 0
        if shutil.disk_usage(destination.parent).free < reserve + ceiling - offset:
            raise PolicyError("insufficient_staging_space")
        headers = {}
        if resume:
            headers = {"Range": f"bytes={offset}-", "If-Range": resume["etag"]}
        elif validators and destination.exists():
            if validators.get("etag"):
                headers["If-None-Match"] = validators["etag"]
            if validators.get("last_modified"):
                headers["If-Modified-Since"] = validators["last_modified"]
        keep_partial = False
        try:
            with self.get(url, headers) as response:
                if response.status == 304:
                    if not destination.exists() or not validators:
                        raise ValueError("304_without_cached_artifact")
                    if validators.get("sha256") != file_hash(destination):
                        raise ValueError("cached_artifact_hash_mismatch")
                    return {**validators, "not_modified": True}
                if response.status == 206:
                    match = re.fullmatch(
                        r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", "")
                    )
                    if (
                        not resume
                        or not match
                        or int(match[1]) != offset
                        or int(match[2]) != int(match[3]) - 1
                        or int(match[3]) != resume["total"]
                        or response.headers.get("ETag") != resume["etag"]
                        or response.url != resume["final_url"]
                    ):
                        raise ValueError("invalid_partial_artifact")
                    total = resume["total"]
                    mode = "ab"
                else:
                    # Ignored Range or changed validator means a complete safe restart.
                    offset = 0
                    mode = "wb"
                    total = response.expected
                if total is not None and total > ceiling:
                    raise PolicyError("artifact_byte_limit")
                etag = response.headers.get("ETag")
                if etag and not etag.startswith("W/") and total is not None:
                    state_path.write_text(
                        json.dumps(
                            {"url": url, "final_url": response.url, "etag": etag, "total": total}
                        )
                    )
                    keep_partial = True
                else:
                    state_path.unlink(missing_ok=True)
                count = offset
                with temporary.open(mode) as output:
                    while chunk := response.read(1024 * 1024):
                        if shutil.disk_usage(destination.parent).free < reserve + len(chunk):
                            raise PolicyError("insufficient_staging_space")
                        count += len(chunk)
                        if count > ceiling:
                            raise PolicyError("artifact_byte_limit")
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if total is not None and count != total:
                    raise OSError("incomplete_artifact")
                digest = file_hash(temporary)
                os.replace(temporary, destination)
                state_path.unlink(missing_ok=True)
                return {
                    "sha256": digest,
                    "bytes": count,
                    "etag": etag,
                    "last_modified": response.headers.get("Last-Modified"),
                    "not_modified": False,
                    "url": response.url,
                }
        except (OSError, http.client.HTTPException):
            # Only a URL/strong-validator/size-bound partial can survive an I/O failure.
            if not keep_partial:
                temporary.unlink(missing_ok=True)
                state_path.unlink(missing_ok=True)
            raise
        except BaseException:
            temporary.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
            raise


def file_hash(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validate_zip(path, *, max_members=10000, max_expanded_bytes=200 * 1024**3):
    with ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > max_members:
            raise PolicyError("archive_member_limit")
        total = 0
        for member in members:
            name = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (
                name.is_absolute()
                or ".." in name.parts
                or "\\" in member.filename
                or (mode & 0o170000) not in {0, 0o100000, 0o040000}
                or re.match(r"^[a-zA-Z]:", member.filename)
                or any(
                    part.upper().split(".")[0]
                    in {
                        "CON",
                        "PRN",
                        "AUX",
                        "NUL",
                        *(f"COM{i}" for i in range(1, 10)),
                        *(f"LPT{i}" for i in range(1, 10)),
                    }
                    for part in name.parts
                )
            ):
                raise PolicyError("unsafe_archive_member")
            total += member.file_size
            if total > max_expanded_bytes:
                raise PolicyError("archive_expansion_limit")
        return members
