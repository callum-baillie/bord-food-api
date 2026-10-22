import hashlib
import io
import json
import socket
from zipfile import ZipFile

import pytest

from bord_food_api.transport import PolicyError, Transport, approved_url, validate_zip

PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class Response(io.BytesIO):
    def __init__(self, body=b"", *, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {"Content-Length": str(len(body))}


def transport(responses, calls, **policy):
    class Connection:
        def __init__(self, host, addresses, timeout):
            calls.append({"host": host, "addresses": addresses, "timeout": timeout})

        def request(self, method, path, headers):
            calls[-1].update(method=method, path=path, headers=headers)

        def getresponse(self):
            return responses.pop(0)

        def close(self):
            pass

    return Transport(
        {
            "mode": "bulk_only",
            "origins": ["https://bulk.example"],
            "max_artifact_bytes": 100,
            **policy,
        },
        connector=Connection,
        resolver=lambda *_a, **_k: PUBLIC,
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://bulk.example/file",
        "https://bulk.example:8080/file",
        "https://user:secret@bulk.example/file",
        "https://bulk.example.evil/file",
        "https://127.0.0.1/file",
        "https://2130706433/file",
        "https://bulk.example./file",
        "https://bulk.example/file#fragment",
        "https://bulk.example/\\escape",
    ],
)
def test_origin_and_url_guard(url):
    with pytest.raises(PolicyError):
        approved_url(url, ["https://bulk.example"])


def test_offline_and_private_dns_block_before_connection():
    calls = []
    client = transport([], calls, mode="offline")
    with pytest.raises(PolicyError, match="disabled"):
        client.get("https://bulk.example/file")
    client.policy["mode"] = "bulk_only"
    client.resolver = lambda *_a, **_k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))
    ]
    with pytest.raises(PolicyError, match="non_public"):
        client.get("https://bulk.example/file")
    assert calls == []


def test_pinned_addresses_redirect_and_cross_origin_secret_stripping():
    calls = []
    client = transport(
        [Response(status=302, headers={"Location": "https://cdn.example/file"}), Response(b"ok")],
        calls,
        origins=["https://bulk.example", "https://cdn.example"],
    )
    with client.get(
        "https://bulk.example/file", {"Authorization": "secret", "Cookie": "private"}
    ) as response:
        assert response.read() == b"ok"
        assert response.url == "https://cdn.example/file"
    assert all(call["addresses"][0][-1][0] == "93.184.216.34" for call in calls)
    assert "Authorization" in calls[0]["headers"]
    assert "Authorization" not in calls[1]["headers"]
    assert "Cookie" not in calls[1]["headers"]


def test_unsafe_redirect_is_rejected():
    client = transport([Response(status=302, headers={"Location": "https://evil.example/x"})], [])
    with pytest.raises(PolicyError):
        client.get("https://bulk.example/file")


def test_streaming_unknown_length_is_bounded_and_counted():
    client = transport(
        [Response(b"abcdef", headers={"Content-Type": "application/json"})],
        [],
        max_artifact_bytes=3,
    )
    with (
        client.get("https://bulk.example/file") as response,
        pytest.raises(PolicyError, match="limit"),
    ):
        response.read()
    assert client.bytes == 4


def test_fetch_atomic_conditional_and_safe_range_restart(tmp_path):
    destination = tmp_path / "artifact"
    destination.write_bytes(b"old")
    calls = []
    client = transport([Response(b"new")], calls)
    saved = client.fetch("https://bulk.example/file", destination)
    assert destination.read_bytes() == b"new"
    assert saved["sha256"] == hashlib.sha256(b"new").hexdigest()
    client = transport([Response(status=304, headers={})], calls)
    saved["etag"] = '"v1"'
    assert client.fetch("https://bulk.example/file", destination, validators=saved)["not_modified"]
    assert calls[-1]["headers"]["If-None-Match"] == '"v1"'
    (tmp_path / "artifact.part").write_bytes(b"ne")
    (tmp_path / "artifact.part.json").write_text(
        json.dumps(
            {
                "url": "https://bulk.example/file",
                "final_url": "https://bulk.example/file",
                "etag": '"v2"',
                "total": 3,
            }
        )
    )
    # Ignoring Range is safe: overwrite the private partial, never append a full body.
    client = transport([Response(b"yes", headers={"Content-Length": "3", "ETag": '"v3"'})], calls)
    client.fetch("https://bulk.example/file", destination)
    assert calls[-1]["headers"]["Range"] == "bytes=2-"
    assert destination.read_bytes() == b"yes"
    assert not list(tmp_path.glob("*.part*"))


def test_validator_bound_range_resume_and_reject_mismatched_range(tmp_path):
    destination = tmp_path / "artifact"
    partial, metadata = tmp_path / "artifact.part", tmp_path / "artifact.part.json"
    state = {
        "url": "https://bulk.example/file",
        "final_url": "https://bulk.example/file",
        "etag": '"v1"',
        "total": 6,
    }
    partial.write_bytes(b"abc")
    metadata.write_text(json.dumps(state))
    calls = []
    client = transport(
        [
            Response(
                b"def",
                status=206,
                headers={"Content-Length": "3", "ETag": '"v1"', "Content-Range": "bytes 3-5/6"},
            )
        ],
        calls,
    )
    client.fetch(state["url"], destination)
    assert destination.read_bytes() == b"abcdef"
    assert calls[0]["headers"]["If-Range"] == '"v1"'
    partial.write_bytes(b"abc")
    metadata.write_text(json.dumps(state))
    client = transport(
        [
            Response(
                b"def",
                status=206,
                headers={"Content-Length": "3", "ETag": '"v2"', "Content-Range": "bytes 3-5/6"},
            )
        ],
        [],
    )
    with pytest.raises(ValueError, match="invalid_partial"):
        client.fetch(state["url"], destination)
    assert destination.read_bytes() == b"abcdef"
    assert not partial.exists()


def test_archive_traversal_expansion_and_symlink_are_rejected(tmp_path):
    archive = tmp_path / "bad.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("../escape.json", "{}")
    with pytest.raises(PolicyError, match="unsafe"):
        validate_zip(archive)
    with ZipFile(archive, "w") as output:
        output.writestr("okay.json", "x" * 100)
    with pytest.raises(PolicyError, match="expansion"):
        validate_zip(archive, max_expanded_bytes=10)


def test_policy_revocation_is_checked_before_next_chunk():
    allowed = True

    def check():
        if not allowed:
            raise PolicyError("operator_paused")

    client = transport([Response(b"secret body")], [], _check=check)
    with client.get("https://bulk.example/file") as response:
        allowed = False
        with pytest.raises(PolicyError, match="paused"):
            response.read()
    assert client.bytes == 0


def test_interrupted_strong_validator_transfer_preserves_resumable_partial(tmp_path):
    class Interrupted(Response):
        def read(self, size=-1):
            if self.tell():
                raise OSError("fixture disconnect")
            return super().read(3)

    destination = tmp_path / "download"
    destination.write_bytes(b"old good data")
    client = transport([Interrupted(b"abc", headers={"Content-Length": "6", "ETag": '"v1"'})], [])
    with pytest.raises(OSError):
        client.fetch("https://bulk.example/file", destination)
    assert destination.read_bytes() == b"old good data"
    assert (tmp_path / "download.part").read_bytes() == b"abc"
    client = transport(
        [
            Response(
                b"def",
                status=206,
                headers={"Content-Length": "3", "ETag": '"v1"', "Content-Range": "bytes 3-5/6"},
            )
        ],
        [],
    )
    assert client.fetch("https://bulk.example/file", destination)["bytes"] == 6
    assert destination.read_bytes() == b"abcdef"


def test_crawler_redirect_notice_does_not_request_new_origin_or_expose_secret_in_error():
    from bord_food_api.crawl_history import exception_details
    from bord_food_api.transport import RedirectNotice

    calls = []
    client = transport(
        [
            Response(
                status=301,
                headers={"Location": "https://canonical.example/store?token=synthetic-secret"},
            )
        ],
        calls,
        max_redirects=0,
        report_redirects=True,
    )
    with pytest.raises(RedirectNotice) as caught:
        client.get("https://bulk.example/store")
    assert len(calls) == 1
    assert "synthetic-secret" not in str(caught.value)
    details = exception_details(caught.value)
    assert details["reason"] == "redirect_requires_review" and details["http_status"] == 301
    assert "synthetic-secret" not in json.dumps(details)
