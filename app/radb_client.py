"""IRR API client for fetching prefixes from Internet Routing Registries."""

import logging
import re
import socket
from dataclasses import dataclass, field
from typing import List, Set, Tuple, Dict, Any, Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger("app.radb_client")

# WHOIS servers for IRR sources (port 43)
WHOIS_SERVERS = {
    'RADB': 'whois.radb.net',
    'ARIN': 'rr.arin.net',
    'APNIC': 'whois.apnic.net',
    'LACNIC': 'irr.lacnic.net',
    'AFRINIC': 'whois.afrinic.net',
    'NTTCOM': 'rr.ntt.net',
}

# RIPE uses REST API (more reliable than WHOIS for RIPE data)
RIPE_REST_URL = 'https://rest.db.ripe.net'


@dataclass
class PrefixResult:
    """Result of fetching prefixes from IRR."""
    ipv4_prefixes: Set[str] = field(default_factory=set)
    ipv6_prefixes: Set[str] = field(default_factory=set)
    sources_queried: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class RADBClientError(Exception):
    """Base exception for IRR client errors."""
    pass


class RADBAPIError(RADBClientError):
    """Error from IRR API."""
    pass


class RADBClient:
    """Client for querying IRR databases for routing prefixes."""

    def __init__(
        self,
        base_url: str = "https://rest.db.ripe.net",
        timeout: int = 60,
        max_retries: int = 3,
    ):
        """
        Initialize the IRR client.

        Args:
            base_url: Base URL for IRR API (default: RIPE REST API).
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retry attempts.
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'irr-automation/1.0',
        })

    def fetch_prefixes(
        self,
        target: str,
        irr_sources: List[str],
    ) -> PrefixResult:
        """
        Fetch IPv4 and IPv6 prefixes for a target ASN from multiple IRR sources.

        Args:
            target: ASN to query (e.g., "AS15169").
            irr_sources: List of IRR sources to query (e.g., ["RIPE", "RADB"]).

        Returns:
            PrefixResult with merged prefixes from all sources.
        """
        result = PrefixResult()

        for source in irr_sources:
            try:
                v4, v6 = self._query_source(target, source)
                result.ipv4_prefixes.update(v4)
                result.ipv6_prefixes.update(v6)
                result.sources_queried.append(source)
                logger.info(
                    f"Fetched from {source}: {len(v4)} IPv4, {len(v6)} IPv6 prefixes",
                    extra={'context': {
                        'target': target,
                        'source': source,
                        'ipv4_count': len(v4),
                        'ipv6_count': len(v6),
                    }}
                )
            except RADBClientError as e:
                error_msg = f"Failed to query {source}: {e}"
                result.errors.append(error_msg)
                logger.warning(
                    error_msg,
                    extra={'context': {'target': target, 'source': source}}
                )

        logger.info(
            f"Total prefixes for {target}: {len(result.ipv4_prefixes)} IPv4, "
            f"{len(result.ipv6_prefixes)} IPv6 from {len(result.sources_queried)} sources",
            extra={'context': {
                'target': target,
                'total_ipv4': len(result.ipv4_prefixes),
                'total_ipv6': len(result.ipv6_prefixes),
                'sources': result.sources_queried,
            }}
        )

        return result

    def _query_source(self, target: str, source: str) -> Tuple[Set[str], Set[str]]:
        """
        Query a single IRR source for prefixes.

        Args:
            target: ASN to query.
            source: IRR source name.

        Returns:
            Tuple of (IPv4 prefixes, IPv6 prefixes).
        """
        return self._query_with_retry(target, source)

    def _query_with_retry(self, target: str, source: str) -> Tuple[Set[str], Set[str]]:
        """Query with retry logic."""

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((requests.RequestException, RADBAPIError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _do_query():
            return self._execute_query(target, source)

        try:
            return _do_query()
        except requests.RequestException as e:
            raise RADBAPIError(f"Request failed after {self.max_retries} attempts: {e}")

    def _execute_query(self, target: str, source: str) -> Tuple[Set[str], Set[str]]:
        """Execute the actual API query."""
        source_upper = source.upper()

        # Use RIPE REST API for RIPE source (most reliable)
        if source_upper == 'RIPE':
            return self._query_ripe_rest(target)

        # Use WHOIS protocol for other IRR sources
        if source_upper in WHOIS_SERVERS:
            return self._query_whois(target, source_upper)

        # Fallback: try RIPE REST API with source parameter for unknown sources
        # This works for sources mirrored by RIPE
        logger.warning(
            f"Unknown IRR source {source}, trying RIPE mirror",
            extra={'context': {'source': source, 'target': target}}
        )
        return self._query_ripe_rest(target, source_lower=source.lower())

    def _query_whois(self, target: str, source: str) -> Tuple[Set[str], Set[str]]:
        """
        Query IRR via WHOIS protocol (port 43).

        Args:
            target: ASN to query (e.g., "AS15169").
            source: IRR source name (e.g., "RADB").

        Returns:
            Tuple of (IPv4 prefixes, IPv6 prefixes).
        """
        server = WHOIS_SERVERS.get(source)
        if not server:
            raise RADBAPIError(f"No WHOIS server configured for source: {source}")

        # WHOIS query format: "-i origin AS15169" returns route/route6 objects
        # Some servers also support "-s SOURCE" to specify the source
        query = f"-i origin {target}\r\n"

        logger.debug(
            f"Querying WHOIS server {server}:43",
            extra={'context': {'server': server, 'target': target, 'source': source}}
        )

        try:
            # Connect to WHOIS server
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((server, 43))

            # Send query
            sock.sendall(query.encode('utf-8'))

            # Receive response
            response_data = b''
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk

            sock.close()

            response_text = response_data.decode('utf-8', errors='replace')

        except socket.timeout:
            raise RADBAPIError(f"WHOIS query to {server} timed out after {self.timeout}s")
        except socket.error as e:
            raise RADBAPIError(f"WHOIS connection to {server} failed: {e}")

        return self._parse_whois_response(response_text)

    def _parse_whois_response(self, response: str) -> Tuple[Set[str], Set[str]]:
        """
        Parse WHOIS response to extract route/route6 prefixes.

        WHOIS responses contain objects in the format:
            route:          192.0.2.0/24
            origin:         AS15169
            ...

            route6:         2001:db8::/32
            origin:         AS15169
            ...

        Args:
            response: Raw WHOIS response text.

        Returns:
            Tuple of (IPv4 prefixes, IPv6 prefixes).
        """
        ipv4_prefixes: Set[str] = set()
        ipv6_prefixes: Set[str] = set()

        # Regex patterns to extract prefixes
        # route: prefix (IPv4)
        route_pattern = re.compile(r'^route:\s+(\S+)', re.MULTILINE | re.IGNORECASE)
        # route6: prefix (IPv6)
        route6_pattern = re.compile(r'^route6:\s+(\S+)', re.MULTILINE | re.IGNORECASE)

        # Find all IPv4 routes
        for match in route_pattern.finditer(response):
            prefix = match.group(1).strip()
            if prefix and '/' in prefix:
                ipv4_prefixes.add(prefix)

        # Find all IPv6 routes
        for match in route6_pattern.finditer(response):
            prefix = match.group(1).strip()
            if prefix and '/' in prefix:
                ipv6_prefixes.add(prefix)

        logger.debug(
            f"Parsed WHOIS response: {len(ipv4_prefixes)} IPv4, {len(ipv6_prefixes)} IPv6",
            extra={'context': {
                'ipv4_count': len(ipv4_prefixes),
                'ipv6_count': len(ipv6_prefixes),
            }}
        )

        return ipv4_prefixes, ipv6_prefixes

    def _query_ripe_rest(
        self,
        target: str,
        source_lower: str = 'ripe'
    ) -> Tuple[Set[str], Set[str]]:
        """
        Query RIPE REST API for prefixes.

        The RIPE REST API is the most reliable public IRR API.
        It can query RIPE and some mirrored sources.

        Args:
            target: ASN to query (e.g., "AS15169").
            source_lower: Source name in lowercase.

        Returns:
            Tuple of (IPv4 prefixes, IPv6 prefixes).
        """
        ipv4_prefixes: Set[str] = set()
        ipv6_prefixes: Set[str] = set()

        # Query for IPv4 routes
        v4 = self._query_ripe_rest_type(target, source_lower, 'route')
        ipv4_prefixes.update(v4)

        # Query for IPv6 routes
        v6 = self._query_ripe_rest_type(target, source_lower, 'route6')
        ipv6_prefixes.update(v6)

        return ipv4_prefixes, ipv6_prefixes

    def _query_ripe_rest_type(
        self,
        target: str,
        source: str,
        obj_type: str
    ) -> Set[str]:
        """
        Query RIPE REST API for a specific object type.

        Args:
            target: ASN to query.
            source: Source name (lowercase).
            obj_type: Object type ('route' or 'route6').

        Returns:
            Set of prefixes.
        """
        # Use RIPE REST API
        url = f"https://rest.db.ripe.net/search.json"
        params = {
            'source': source,
            'query-string': target,
            'inverse-attribute': 'origin',
            'type-filter': obj_type,
        }

        logger.debug(
            f"Querying RIPE REST API: {url}",
            extra={'context': {'params': params}}
        )

        response = self._session.get(
            url,
            params=params,
            timeout=self.timeout,
        )

        # Handle 404 (no results)
        if response.status_code == 404:
            return set()

        # Handle errors
        if response.status_code != 200:
            # Try to parse error message
            try:
                data = response.json()
                error_msgs = data.get('errormessages', {}).get('errormessage', [])
                if error_msgs:
                    error_text = error_msgs[0].get('text', 'Unknown error')
                    # "No entries found" is not an error, just no results
                    if 'no entries' in error_text.lower():
                        return set()
                    raise RADBAPIError(f"API error: {error_text}")
            except (ValueError, KeyError):
                pass
            raise RADBAPIError(
                f"API returned status {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as e:
            raise RADBAPIError(f"Invalid JSON response: {e}")

        return self._parse_ripe_response(data, obj_type)

    def _parse_ripe_response(self, data: dict, obj_type: str) -> Set[str]:
        """
        Parse RIPE REST API response to extract prefixes.

        Args:
            data: JSON response from RIPE REST API.
            obj_type: Object type ('route' or 'route6').

        Returns:
            Set of prefixes.
        """
        prefixes: Set[str] = set()

        objects = data.get('objects', {}).get('object', [])

        for obj in objects:
            if obj.get('type') != obj_type:
                continue

            attributes = obj.get('attributes', {}).get('attribute', [])
            for attr in attributes:
                if attr.get('name') == obj_type:
                    prefix = attr.get('value')
                    if prefix:
                        prefixes.add(prefix)
                    break

        return prefixes

    def _parse_response(self, data: dict) -> Tuple[Set[str], Set[str]]:
        """
        Parse generic IRR API response to extract prefixes.

        This method handles the format specified in the requirements doc.

        Args:
            data: JSON response from IRR API.

        Returns:
            Tuple of (IPv4 prefixes, IPv6 prefixes).
        """
        ipv4_prefixes: Set[str] = set()
        ipv6_prefixes: Set[str] = set()

        objects = data.get('objects', [])

        for obj in objects:
            obj_type = obj.get('type', '')
            attributes = obj.get('attributes', {})

            if obj_type == 'route':
                prefix = attributes.get('route')
                if prefix:
                    ipv4_prefixes.add(prefix)

            elif obj_type == 'route6':
                prefix = attributes.get('route6')
                if prefix:
                    ipv6_prefixes.add(prefix)

        return ipv4_prefixes, ipv6_prefixes

    def close(self):
        """Close the HTTP session."""
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
