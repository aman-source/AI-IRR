# Multi-IRR Source Query Architecture

This document explains how the IRR Automation tool queries 7 different Internet Routing Registry sources and merges the results.

## Overview

The tool supports querying multiple IRR databases to get comprehensive routing prefix data. Each source may have different or overlapping data, so results are merged using a **set union** operation to eliminate duplicates.

---

## The 7 IRR Sources

### 1. RIPE (Réseaux IP Européens)

| Property | Value |
|----------|-------|
| **Type** | Regional Internet Registry (RIR) |
| **Coverage** | Europe, Middle East, Central Asia |
| **Protocol** | REST API |
| **Endpoint** | `https://rest.db.ripe.net/search.json` |
| **Query Method** | HTTP GET with inverse lookup |

**How it works:**
```
GET https://rest.db.ripe.net/search.json?
    source=ripe&
    query-string=AS15169&
    inverse-attribute=origin&
    type-filter=route
```

**Response format:** JSON with nested objects containing route attributes.

---

### 2. RADB (Routing Assets Database)

| Property | Value |
|----------|-------|
| **Type** | Internet Routing Registry |
| **Coverage** | Global (Merit Network) |
| **Protocol** | WHOIS (TCP port 43) |
| **Server** | `whois.radb.net` |
| **Query Method** | Socket connection |

**How it works:**
```
Connect to whois.radb.net:43
Send: "-i origin AS15169\r\n"
Receive: Text with route/route6 objects
```

**Response format:** Plain text RPSL objects.

---

### 3. ARIN (American Registry for Internet Numbers)

| Property | Value |
|----------|-------|
| **Type** | Regional Internet Registry (RIR) |
| **Coverage** | North America |
| **Protocol** | WHOIS (TCP port 43) |
| **Server** | `rr.arin.net` |
| **Query Method** | Socket connection |

**How it works:**
```
Connect to rr.arin.net:43
Send: "-i origin AS15169\r\n"
Receive: Text with route/route6 objects
```

---

### 4. APNIC (Asia-Pacific Network Information Centre)

| Property | Value |
|----------|-------|
| **Type** | Regional Internet Registry (RIR) |
| **Coverage** | Asia Pacific |
| **Protocol** | WHOIS (TCP port 43) |
| **Server** | `whois.apnic.net` |
| **Query Method** | Socket connection |

**How it works:**
```
Connect to whois.apnic.net:43
Send: "-i origin AS15169\r\n"
Receive: Text with route/route6 objects
```

---

### 5. LACNIC (Latin America and Caribbean Network Information Centre)

| Property | Value |
|----------|-------|
| **Type** | Regional Internet Registry (RIR) |
| **Coverage** | Latin America & Caribbean |
| **Protocol** | WHOIS (TCP port 43) |
| **Server** | `irr.lacnic.net` |
| **Query Method** | Socket connection |

**How it works:**
```
Connect to irr.lacnic.net:43
Send: "-i origin AS15169\r\n"
Receive: Text with route/route6 objects
```

---

### 6. AFRINIC (African Network Information Centre)

| Property | Value |
|----------|-------|
| **Type** | Regional Internet Registry (RIR) |
| **Coverage** | Africa |
| **Protocol** | WHOIS (TCP port 43) |
| **Server** | `whois.afrinic.net` |
| **Query Method** | Socket connection |

**How it works:**
```
Connect to whois.afrinic.net:43
Send: "-i origin AS15169\r\n"
Receive: Text with route/route6 objects
```

---

### 7. NTTCOM (NTT Communications)

| Property | Value |
|----------|-------|
| **Type** | Internet Routing Registry |
| **Coverage** | NTT Communications network |
| **Protocol** | WHOIS (TCP port 43) |
| **Server** | `rr.ntt.net` |
| **Query Method** | Socket connection |

**How it works:**
```
Connect to rr.ntt.net:43
Send: "-i origin AS15169\r\n"
Receive: Text with route/route6 objects
```

---

## Query Flow Diagram

```
                    ┌─────────────────────────────────────┐
                    │     fetch_prefixes("AS15169",       │
                    │  ["RIPE","RADB","ARIN","APNIC",...])│
                    └─────────────────┬───────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│     RIPE      │           │     RADB      │           │     ARIN      │
│   REST API    │           │    WHOIS      │           │    WHOIS      │
│               │           │               │           │               │
│ GET /search   │           │ whois.radb    │           │ rr.arin.net   │
│   .json       │           │   .net:43     │           │     :43       │
└───────┬───────┘           └───────┬───────┘           └───────┬───────┘
        │                           │                           │
        ▼                           ▼                           ▼
  {8.8.8.0/24,                {8.8.8.0/24,                {8.34.208.0/20}
   8.8.4.0/24}                 172.217.0.0/16}
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────────┐
                    │          SET UNION                  │
                    │                                     │
                    │  ipv4_prefixes.update(source_v4)    │
                    │  ipv6_prefixes.update(source_v6)    │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │         FINAL RESULT                │
                    │                                     │
                    │  IPv4: {8.8.8.0/24, 8.8.4.0/24,    │
                    │         172.217.0.0/16,             │
                    │         8.34.208.0/20}              │
                    │                                     │
                    │  IPv6: {2001:4860::/32, ...}        │
                    └─────────────────────────────────────┘
```

---

## Union Merge Strategy

### Why Union?

Different IRR sources may contain:
- **Overlapping data**: Same prefix registered in multiple IRRs
- **Unique data**: Prefixes only in regional RIR (e.g., ARIN-only routes)
- **Stale data**: Old entries not yet cleaned up

Using **set union** ensures:
1. No duplicates in the final result
2. Complete coverage from all sources
3. Simple and fast merge operation

### Implementation

```python
# In radb_client.py - fetch_prefixes()

def fetch_prefixes(self, target: str, irr_sources: List[str]) -> PrefixResult:
    result = PrefixResult()

    for source in irr_sources:
        try:
            v4, v6 = self._query_source(target, source)

            # UNION: Add all prefixes from this source
            result.ipv4_prefixes.update(v4)  # Set union
            result.ipv6_prefixes.update(v6)  # Set union

            result.sources_queried.append(source)
        except RADBClientError as e:
            result.errors.append(f"Failed to query {source}: {e}")

    return result
```

### Example Merge

```
Source 1 (RIPE):  {8.8.8.0/24, 8.8.4.0/24}
Source 2 (RADB):  {8.8.8.0/24, 172.217.0.0/16}    # 8.8.8.0/24 is duplicate
Source 3 (ARIN):  {8.34.208.0/20}

Union Result:     {8.8.8.0/24, 8.8.4.0/24, 172.217.0.0/16, 8.34.208.0/20}
                  └── 4 unique prefixes (duplicate removed)
```

---

## Protocol Details

### REST API (RIPE only)

```python
def _query_ripe_rest(self, target: str) -> Tuple[Set[str], Set[str]]:
    # Query IPv4 routes
    url = "https://rest.db.ripe.net/search.json"
    params = {
        'source': 'ripe',
        'query-string': target,        # e.g., "AS15169"
        'inverse-attribute': 'origin', # Find by origin ASN
        'type-filter': 'route',        # IPv4 routes
    }
    response = self._session.get(url, params=params)
    # Parse JSON response...
```

**Advantages:**
- Structured JSON response
- HTTP caching friendly
- Easy error handling

### WHOIS Protocol (All others)

```python
def _query_whois(self, target: str, source: str) -> Tuple[Set[str], Set[str]]:
    server = WHOIS_SERVERS[source]  # e.g., "whois.radb.net"

    # Create socket connection
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(self.timeout)
    sock.connect((server, 43))

    # Send query
    query = f"-i origin {target}\r\n"  # Inverse lookup by origin
    sock.sendall(query.encode('utf-8'))

    # Receive response
    response = b''
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        response += chunk

    sock.close()
    return self._parse_whois_response(response.decode())
```

**WHOIS Response Parsing:**
```python
def _parse_whois_response(self, response: str) -> Tuple[Set[str], Set[str]]:
    ipv4 = set()
    ipv6 = set()

    # Extract IPv4 prefixes: "route: 8.8.8.0/24"
    for match in re.finditer(r'^route:\s+(\S+)', response, re.MULTILINE | re.IGNORECASE):
        ipv4.add(match.group(1))

    # Extract IPv6 prefixes: "route6: 2001:4860::/32"
    for match in re.finditer(r'^route6:\s+(\S+)', response, re.MULTILINE | re.IGNORECASE):
        ipv6.add(match.group(1))

    return ipv4, ipv6
```

---

## Error Handling

Each source is queried independently. If one fails, others continue:

```python
for source in irr_sources:
    try:
        v4, v6 = self._query_source(target, source)
        result.ipv4_prefixes.update(v4)
        result.ipv6_prefixes.update(v6)
        result.sources_queried.append(source)
    except RADBClientError as e:
        # Log error but continue with other sources
        result.errors.append(f"Failed to query {source}: {e}")
        logger.warning(f"Failed to query {source}: {e}")

# Return partial results even if some sources failed
return result
```

---

## Configuration

In `config.yaml`:

```yaml
# Query order matters - faster/more reliable sources first
irr_sources:
  - RIPE      # Primary - REST API, fast
  - RADB      # Global coverage
  - ARIN      # North America
  - APNIC     # Asia Pacific
  - LACNIC    # Latin America
  - AFRINIC   # Africa
  - NTTCOM    # NTT network
```

---

## Performance Considerations

| Source | Protocol | Typical Latency | Reliability |
|--------|----------|-----------------|-------------|
| RIPE | REST | 100-500ms | High |
| RADB | WHOIS | 200-800ms | High |
| ARIN | WHOIS | 200-600ms | High |
| APNIC | WHOIS | 300-1000ms | Medium |
| LACNIC | WHOIS | 400-1200ms | Medium |
| AFRINIC | WHOIS | 500-1500ms | Medium |
| NTTCOM | WHOIS | 200-800ms | High |

**Optimization tips:**
- Put fastest sources first in config
- Set appropriate timeout (default: 60s)
- Use retry logic for transient failures
