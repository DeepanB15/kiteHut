"""
GitHub Webhook Handler for RepoLens (Layer 11).
"""

import hashlib
import hmac
import logging
from typing import Any, Dict, Optional, Tuple

from app.github.models.github_models import PRFileChange, PRReviewReport, PRState, PullRequestInfo
from app.github.pr_analyzer import PullRequestAnalyzer

logger = logging.getLogger("repolens.github.webhooks")


class GitHubWebhookHandler:
    """Validates and handles inbound GitHub Webhook notifications."""

    def __init__(self, webhook_secret: Optional[str] = None):
        self.secret = webhook_secret

    def verify_signature(self, payload_bytes: bytes, signature_header: Optional[str]) -> bool:
        """Validate HMAC SHA-256 signature from GitHub 'X-Hub-Signature-256'."""
        if not self.secret:
            # No secret configured -> accept
            return True

        if not signature_header:
            logger.warning("Missing X-Hub-Signature-256 header")
            return False

        if not signature_header.startswith("sha256="):
            return False

        expected_sig = signature_header.split("sha256=")[-1]
        computed_sig = hmac.new(
            self.secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_sig, computed_sig)

    def parse_pull_request_event(self, payload: Dict[str, Any]) -> Tuple[PullRequestInfo, str]:
        """Extract PullRequestInfo and action string from webhook payload."""
        action = payload.get("action", "")
        pr_data = payload.get("pull_request", {})

        pr_info = PullRequestInfo(
            number=pr_data.get("number", 0),
            title=pr_data.get("title", "Untitled PR"),
            body=pr_data.get("body", "") or "",
            head_sha=pr_data.get("head", {}).get("sha", "0000000"),
            base_sha=pr_data.get("base", {}).get("sha", "0000000"),
            head_branch=pr_data.get("head", {}).get("ref", "feature"),
            base_branch=pr_data.get("base", {}).get("ref", "main"),
            author=pr_data.get("user", {}).get("login", "unknown"),
            state=PRState.OPEN if pr_data.get("state") == "open" else PRState.CLOSED,
            html_url=pr_data.get("html_url", ""),
        )

        return pr_info, action
