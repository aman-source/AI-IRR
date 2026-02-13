"""Proxy client that calls the deployed IRR Prefix Lookup API instead of running bgpq4 locally.

Use this when bgpq4 is not available on the local machine.
Set `api_url` in config.yaml to enable:

    api_url: "https://your-deployed-api.azurecontainerapps.io"
"""

import logging

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from app.bgpq4_client import PrefixResult, BGPQ4ClientError

logger = logging.getLogger("app.api_proxy_client")


class APIProxyClient:
    """Client that fetches prefixes via the deployed IRR Prefix Lookup API."""

    def __init__(
        self,
        api_url: str,
        timeout: int = 120,
        max_retries: int = 3,
    ):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "irr-automation/2.0 (proxy)",
        })

    def fetch_prefixes(self, target: str) -> PrefixResult:
        """Fetch prefixes by calling the deployed cloud API.

        Same interface as BGPQ4Client.fetch_prefixes().
        """
        return self._fetch_with_retry(target)

    def _fetch_with_retry(self, target: str) -> PrefixResult:
        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((requests.RequestException, BGPQ4ClientError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _do_fetch():
            return self._execute_fetch(target)

        try:
            return _do_fetch()
        except requests.RequestException as e:
            raise BGPQ4ClientError(
                f"API proxy request failed after {self.max_retries} attempts: {e}"
            )

    def _execute_fetch(self, target: str) -> PrefixResult:
        url = f"{self.api_url}/api/v1/fetch"

        logger.info(
            f"Calling API proxy: {url}",
            extra={"context": {"target": target}},
        )

        response = self._session.post(
            url,
            json={"target": target},
            timeout=self.timeout,
        )

        if response.status_code == 422:
            data = response.json()
            detail = data.get("detail", "Validation error")
            raise BGPQ4ClientError(f"API validation error: {detail}")

        if response.status_code == 502:
            data = response.json()
            detail = data.get("detail", {})
            raise BGPQ4ClientError(
                f"BGPQ4 query failed via API: {detail.get('errors', [])}"
            )

        if response.status_code != 200:
            raise BGPQ4ClientError(
                f"API returned status {response.status_code}: {response.text[:200]}"
            )

        data = response.json()

        result = PrefixResult(
            ipv4_prefixes=set(data.get("ipv4_prefixes", [])),
            ipv6_prefixes=set(data.get("ipv6_prefixes", [])),
            sources_queried=data.get("sources_queried", []),
            errors=data.get("errors", []),
        )

        logger.info(
            f"API proxy returned {len(result.ipv4_prefixes)} IPv4, "
            f"{len(result.ipv6_prefixes)} IPv6 prefixes",
            extra={"context": {
                "target": target,
                "ipv4_count": len(result.ipv4_prefixes),
                "ipv6_count": len(result.ipv6_prefixes),
                "sources": result.sources_queried,
            }},
        )

        return result

    def close(self):
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
