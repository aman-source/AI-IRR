"""Microsoft Teams alert integration via Power Automate webhook."""

import logging
from datetime import datetime, timezone
from typing import Optional

import requests

from app.diff import DiffResult

logger = logging.getLogger("app.teams")


class TeamsNotifier:
    """Posts IRR prefix change alerts to Teams via a Power Automate webhook."""

    def __init__(self, webhook_url: str, timeout: int = 15):
        self.webhook_url = webhook_url
        self.timeout = timeout

    def notify(self, target: str, diff: DiffResult, ticket_id: Optional[str] = None, dry_run: bool = False) -> bool:
        """
        Send a Teams alert for detected prefix changes.

        Args:
            target: ASN or AS-SET that changed.
            diff: The diff result with change details.
            ticket_id: Ticket ID if one was created, else None.
            dry_run: If True, log but do not actually send.

        Returns:
            True if the alert was sent (or dry-run), False on error.
        """
        if not self.webhook_url:
            logger.debug("Teams webhook URL not configured, skipping notification")
            return False

        payload = self._build_payload(target, diff, ticket_id)

        if dry_run:
            logger.info(
                f"[DRY-RUN] Would send Teams alert for {target}",
                extra={"context": {"target": target, "diff_hash": diff.diff_hash}},
            )
            return True

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.info(
                f"Teams alert sent for {target}",
                extra={"context": {"target": target, "status_code": response.status_code}},
            )
            return True
        except requests.RequestException as e:
            logger.error(
                f"Failed to send Teams alert for {target}: {e}",
                extra={"context": {"target": target, "error": str(e)}},
            )
            return False

    def _build_payload(self, target: str, diff: DiffResult, ticket_id: Optional[str]) -> dict:
        """Build the Adaptive Card JSON payload sent to the Power Automate webhook."""
        change_lines = []
        if diff.added_v4:
            change_lines.append(f"- Added {len(diff.added_v4)} IPv4 prefix(es)")
        if diff.removed_v4:
            change_lines.append(f"- Removed {len(diff.removed_v4)} IPv4 prefix(es)")
        if diff.added_v6:
            change_lines.append(f"- Added {len(diff.added_v6)} IPv6 prefix(es)")
        if diff.removed_v6:
            change_lines.append(f"- Removed {len(diff.removed_v6)} IPv6 prefix(es)")

        timestamp = datetime.now(timezone.utc).isoformat()
        changes_text = "\n".join(change_lines) if change_lines else "No changes detected"

        card_body = [
            {
                "type": "TextBlock",
                "text": f"IRR Prefix Change Alert: {target}",
                "weight": "Bolder",
                "size": "Medium",
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Target", "value": target},
                    {"title": "Summary", "value": diff.summary},
                    {"title": "Ticket ID", "value": ticket_id or "N/A"},
                    {"title": "Diff Hash", "value": diff.diff_hash},
                    {"title": "Timestamp", "value": timestamp},
                ],
            },
            {
                "type": "TextBlock",
                "text": "Changes",
                "weight": "Bolder",
            },
            {
                "type": "TextBlock",
                "text": changes_text,
                "wrap": True,
            },
        ]

        MAX_SHOW = 10

        def _prefix_block(label: str, prefixes: list, color: str) -> list:
            blocks = [{"type": "TextBlock", "text": label, "weight": "Bolder", "color": color}]
            shown = prefixes[:MAX_SHOW]
            extra = len(prefixes) - MAX_SHOW
            text = "\n".join(shown)
            if extra > 0:
                text += f"\n… and {extra} more"
            blocks.append({"type": "TextBlock", "text": text, "wrap": True, "fontType": "Monospace"})
            return blocks

        if diff.added_v4:
            card_body += _prefix_block(f"Added IPv4 ({len(diff.added_v4)})", diff.added_v4, "Good")
        if diff.removed_v4:
            card_body += _prefix_block(f"Removed IPv4 ({len(diff.removed_v4)})", diff.removed_v4, "Attention")
        if diff.added_v6:
            card_body += _prefix_block(f"Added IPv6 ({len(diff.added_v6)})", diff.added_v6, "Good")
        if diff.removed_v6:
            card_body += _prefix_block(f"Removed IPv6 ({len(diff.removed_v6)})", diff.removed_v6, "Attention")

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": card_body,
                    },
                }
            ],
        }
