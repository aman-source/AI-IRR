"""AT&T Ticketing API client for IRR Automation."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from app.diff import DiffResult

logger = logging.getLogger("app.ticketing")


@dataclass
class TicketResponse:
    """Response from ticket creation."""
    ticket_id: Optional[str]
    status: str
    is_duplicate: bool = False
    error_message: Optional[str] = None


class TicketingError(Exception):
    """Base exception for ticketing errors."""
    pass


class TicketingAPIError(TicketingError):
    """Error from ticketing API."""
    pass


class TicketingClient:
    """Client for AT&T ticketing API."""

    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize the ticketing client.

        Args:
            base_url: Base URL for ticketing API.
            api_token: Bearer token for authentication.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts.
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'irr-automation/1.0',
        })

    def create_ticket(
        self,
        target: str,
        diff: DiffResult,
        irr_sources: List[str],
        dry_run: bool = False,
    ) -> TicketResponse:
        """
        Create a ticket for detected prefix changes.

        Args:
            target: ASN or AS-SET.
            diff: The diff result containing changes.
            irr_sources: List of IRR sources that were queried.
            dry_run: If True, don't actually create the ticket.

        Returns:
            TicketResponse with ticket ID and status.
        """
        payload = self._build_payload(target, diff, irr_sources)

        if dry_run:
            logger.info(
                f"[DRY-RUN] Would create ticket for {target}",
                extra={'context': {
                    'target': target,
                    'diff_hash': diff.diff_hash,
                    'payload': payload,
                }}
            )
            return TicketResponse(
                ticket_id=None,
                status='dry_run',
            )

        return self._submit_ticket(payload, diff.diff_hash)

    def _build_payload(
        self,
        target: str,
        diff: DiffResult,
        irr_sources: List[str],
    ) -> dict:
        """
        Build the ticket request payload.

        Args:
            target: ASN or AS-SET.
            diff: The diff result.
            irr_sources: List of IRR sources.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        return {
            'type': 'irr_prefix_change',
            'target': target,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'changes': {
                'added_ipv4': diff.added_v4,
                'removed_ipv4': diff.removed_v4,
                'added_ipv6': diff.added_v6,
                'removed_ipv6': diff.removed_v6,
            },
            'summary': diff.summary,
            'irr_sources': irr_sources,
            'diff_hash': diff.diff_hash,
        }

    def _submit_ticket(self, payload: dict, diff_hash: str) -> TicketResponse:
        """Submit ticket with retry logic."""

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((requests.RequestException,)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _do_submit():
            return self._execute_submit(payload, diff_hash)

        try:
            return _do_submit()
        except requests.RequestException as e:
            logger.error(
                f"Failed to create ticket after {self.max_retries} attempts",
                extra={'context': {
                    'error': str(e),
                    'diff_hash': diff_hash,
                }}
            )
            return TicketResponse(
                ticket_id=None,
                status='failed',
                error_message=str(e),
            )

    def _execute_submit(self, payload: dict, diff_hash: str) -> TicketResponse:
        """Execute the actual ticket submission."""
        url = f"{self.base_url}/tickets"

        headers = {
            'Authorization': f'Bearer {self.api_token}',
            'X-Idempotency-Key': diff_hash,
        }

        logger.debug(
            f"Submitting ticket to {url}",
            extra={'context': {
                'target': payload.get('target'),
                'diff_hash': diff_hash,
            }}
        )

        response = self._session.post(
            url,
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )

        # Handle duplicate (409 Conflict) as success
        if response.status_code == 409:
            try:
                data = response.json()
                existing_id = data.get('existing_ticket_id')
                logger.info(
                    f"Ticket already exists: {existing_id}",
                    extra={'context': {
                        'existing_ticket_id': existing_id,
                        'diff_hash': diff_hash,
                    }}
                )
                return TicketResponse(
                    ticket_id=existing_id,
                    status='duplicate',
                    is_duplicate=True,
                )
            except ValueError:
                pass

        # Handle success (201 Created)
        if response.status_code == 201:
            try:
                data = response.json()
                ticket_id = data.get('ticket_id')
                logger.info(
                    f"Ticket created: {ticket_id}",
                    extra={'context': {
                        'ticket_id': ticket_id,
                        'diff_hash': diff_hash,
                    }}
                )
                return TicketResponse(
                    ticket_id=ticket_id,
                    status='created',
                )
            except ValueError:
                pass

        # Handle other status codes as errors
        error_msg = f"API returned status {response.status_code}: {response.text[:200]}"
        logger.error(
            error_msg,
            extra={'context': {
                'status_code': response.status_code,
                'diff_hash': diff_hash,
            }}
        )

        # For server errors (5xx), raise to trigger retry
        if 500 <= response.status_code < 600:
            raise TicketingAPIError(error_msg)

        # For client errors (4xx except 409), return failure without retry
        return TicketResponse(
            ticket_id=None,
            status='failed',
            error_message=error_msg,
        )

    def get_payload(
        self,
        target: str,
        diff: DiffResult,
        irr_sources: List[str],
    ) -> dict:
        """
        Get the payload that would be submitted (for storage/debugging).

        Args:
            target: ASN or AS-SET.
            diff: The diff result.
            irr_sources: List of IRR sources.

        Returns:
            The request payload dictionary.
        """
        return self._build_payload(target, diff, irr_sources)

    def close(self):
        """Close the HTTP session."""
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
