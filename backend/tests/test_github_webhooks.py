"""
Unit Tests for GitHub Webhook Handler (Layer 11).
"""

import hashlib
import hmac
import json
from app.github.models.github_models import PRState
from app.github.webhook_handler import GitHubWebhookHandler


def test_webhook_handler_signature_verification():
    """Verify HMAC SHA-256 signature verification passes for valid signatures and rejects invalid ones."""
    secret = "repolens_secret_key_123"
    handler = GitHubWebhookHandler(webhook_secret=secret)

    payload = json.dumps({"action": "opened", "number": 1}).encode("utf-8")

    # Generate valid signature
    valid_sig = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert handler.verify_signature(payload, valid_sig) is True

    # Tampered signature
    invalid_sig = "sha256=invalid_signature_hex_code_12345"
    assert handler.verify_signature(payload, invalid_sig) is False

    # Missing header
    assert handler.verify_signature(payload, None) is False


def test_webhook_handler_parse_pull_request_event():
    """Verify pull request event extraction from JSON payload."""
    handler = GitHubWebhookHandler()

    payload = {
        "action": "synchronize",
        "pull_request": {
            "number": 55,
            "title": "Update database migrations",
            "body": "Adds new user column",
            "state": "open",
            "head": {"sha": "sha_head_111", "ref": "feature/db"},
            "base": {"sha": "sha_base_000", "ref": "main"},
            "user": {"login": "octocat"},
            "html_url": "https://github.com/octocat/Hello-World/pull/55",
        },
    }

    pr_info, action = handler.parse_pull_request_event(payload)
    assert action == "synchronize"
    assert pr_info.number == 55
    assert pr_info.title == "Update database migrations"
    assert pr_info.head_sha == "sha_head_111"
    assert pr_info.author == "octocat"
    assert pr_info.state == PRState.OPEN
