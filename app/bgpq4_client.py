"""BGPQ4-based IRR client for fetching prefixes from Internet Routing Registries.

Uses the bgpq4 CLI tool (via WSL on Windows) to query IRR databases.
BGPQ4 handles AS-SET expansion, prefix aggregation, and database selection
in a single command, replacing the multi-source WHOIS/REST approach.
"""

import ipaddress
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Set

logger = logging.getLogger("app.bgpq4_client")


def collapse_prefixes(prefixes: Set[str]) -> Set[str]:
    """Collapse/aggregate a set of prefix strings using ipaddress.collapse_addresses().

    Removes covered subnets and merges adjacent networks into the minimal set
    of supernets. Skips any invalid prefix strings.

    Args:
        prefixes: Set of CIDR prefix strings (e.g., {"10.0.0.0/16", "10.0.1.0/24"}).

    Returns:
        Minimal set of non-overlapping, non-adjacent prefix strings.
    """
    networks = []
    for p in prefixes:
        try:
            networks.append(ipaddress.ip_network(p, strict=False))
        except ValueError:
            logger.warning(f"Skipping invalid prefix: {p}")
    try:
        return {str(n) for n in ipaddress.collapse_addresses(networks)}
    except TypeError:
        # collapse_addresses raises TypeError when IPv4 and IPv6 are mixed.
        # Collapse each family separately and union the results.
        v4 = [n for n in networks if n.version == 4]
        v6 = [n for n in networks if n.version == 6]
        return (
            {str(n) for n in ipaddress.collapse_addresses(v4)} |
            {str(n) for n in ipaddress.collapse_addresses(v6)}
        )


@dataclass
class PrefixResult:
    """Result of fetching prefixes from IRR."""
    ipv4_prefixes: Set[str] = field(default_factory=set)
    ipv6_prefixes: Set[str] = field(default_factory=set)
    ipv4_raw_count: int = 0   # prefix count before Python aggregation
    ipv6_raw_count: int = 0   # prefix count before Python aggregation
    sources_queried: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class BGPQ4ClientError(Exception):
    """Base exception for BGPQ4 client errors."""
    pass


class BGPQ4NotFoundError(BGPQ4ClientError):
    """BGPQ4 binary not found."""
    pass


class BGPQ4Client:
    """Client for querying IRR databases via BGPQ4.

    BGPQ4 is called as a subprocess. On Windows, it runs through WSL.
    A single command fetches prefixes for an ASN or AS-SET, with automatic
    AS-SET expansion and optional prefix aggregation.
    """

    def __init__(
        self,
        bgpq4_cmd: List[str] = None,
        timeout: int = 120,
        sources: List[str] = None,
        aggregate: bool = True,
    ):
        """Initialize the BGPQ4 client.

        Args:
            bgpq4_cmd: Command to invoke bgpq4 (e.g., ["wsl", "bgpq4"]).
                        Defaults to ["wsl", "bgpq4"].
            timeout: Subprocess timeout in seconds.
            sources: IRR sources for -S flag (e.g., ["RADB", "RPKI"]).
                     bgpq4 accepts comma-separated sources: -S RADB,RPKI.
            aggregate: Whether to use -A flag for prefix aggregation.
        """
        if bgpq4_cmd is not None:
            self.bgpq4_cmd = bgpq4_cmd
        elif shutil.which("bgpq4"):
            self.bgpq4_cmd = ["bgpq4"]       # native binary (Linux/Docker)
        else:
            self.bgpq4_cmd = ["wsl", "bgpq4"]  # Windows fallback via WSL
        self.timeout = timeout
        if sources is None:
            self.sources = ["RADB"]
        elif not sources:
            raise ValueError("sources must not be empty")
        else:
            self.sources = sources
        self.aggregate = aggregate

    def fetch_prefixes(self, target: str) -> PrefixResult:
        """Fetch IPv4 and IPv6 prefixes for a target ASN or AS-SET.

        Args:
            target: ASN (e.g., "AS15169") or AS-SET (e.g., "AS-GOOGLE").

        Returns:
            PrefixResult with aggregated prefixes.
        """
        target = target.strip().upper()
        result = PrefixResult(sources_queried=list(self.sources))

        # Fetch IPv4
        try:
            v4_raw = self._run_bgpq4(target, ipv6=False)
            result.ipv4_raw_count = len(v4_raw)
            result.ipv4_prefixes = collapse_prefixes(v4_raw)
        except BGPQ4ClientError as e:
            result.errors.append(f"IPv4 query failed: {e}")

        # Fetch IPv6
        try:
            v6_raw = self._run_bgpq4(target, ipv6=True)
            result.ipv6_raw_count = len(v6_raw)
            result.ipv6_prefixes = collapse_prefixes(v6_raw)
        except BGPQ4ClientError as e:
            result.errors.append(f"IPv6 query failed: {e}")

        logger.info(
            f"BGPQ4 fetched for {target}: "
            f"{result.ipv4_raw_count} IPv4 raw → {len(result.ipv4_prefixes)} aggregated, "
            f"{result.ipv6_raw_count} IPv6 raw → {len(result.ipv6_prefixes)} aggregated",
            extra={'context': {
                'target': target,
                'sources': self.sources,
                'ipv4_raw_count': result.ipv4_raw_count,
                'ipv4_count': len(result.ipv4_prefixes),
                'ipv6_raw_count': result.ipv6_raw_count,
                'ipv6_count': len(result.ipv6_prefixes),
            }}
        )

        return result

    def _run_bgpq4(self, target: str, ipv6: bool = False) -> Set[str]:
        """Run bgpq4 and parse JSON output.

        Args:
            target: ASN or AS-SET to query.
            ipv6: If True, query for IPv6 prefixes; otherwise IPv4.

        Returns:
            Set of prefix strings.
        """
        cmd = list(self.bgpq4_cmd)
        cmd.append("-6" if ipv6 else "-4")
        cmd.append("-j")  # JSON output
        cmd.extend(["-S", ",".join(self.sources)])
        cmd.extend(["-l", "pl"])
        cmd.append(target)

        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise BGPQ4ClientError(
                f"bgpq4 timed out after {self.timeout}s for {target}"
            )
        except FileNotFoundError:
            raise BGPQ4NotFoundError(
                f"Command not found: {self.bgpq4_cmd[0]}. "
                f"Ensure bgpq4 is installed (WSL: sudo apt install bgpq4)"
            )

        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            raise BGPQ4ClientError(
                f"bgpq4 exited with code {proc.returncode}: {stderr}"
            )

        return self._parse_json_output(proc.stdout)

    def _parse_json_output(self, output: str) -> Set[str]:
        """Parse BGPQ4 JSON output to extract prefixes.

        BGPQ4 -j output format:
        { "pl": [
            { "prefix": "8.8.8.0/24", "exact": true },
            ...
        ]}
        """
        if not output.strip():
            return set()

        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            raise BGPQ4ClientError(f"Failed to parse bgpq4 JSON output: {e}")

        prefixes = set()
        for entry in data.get("pl", []):
            prefix = entry.get("prefix")
            if prefix:
                prefixes.add(prefix)

        return prefixes

    def close(self):
        """No-op for API compatibility (no persistent connections)."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
