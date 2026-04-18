export interface HealthResponse {
  status: string;
  version: string;
  sources: string[];
}

export interface PrefixResponse {
  target: string;
  ipv4_prefixes: string[];
  ipv6_prefixes: string[];
  ipv4_raw_count: number;
  ipv4_count: number;
  ipv6_raw_count: number;
  ipv6_count: number;
  sources_queried: string[];
  errors: string[];
  query_time_ms: number;
}

export interface OverviewStats {
  total_targets: number;
  last_run_at: number | null;
  recent_diffs: number;
  open_tickets: number;
}

export interface Snapshot {
  id: number;
  target: string;
  target_type: string;
  timestamp: number;
  irr_sources: string[];
  ipv4_prefixes: string[];
  ipv6_prefixes: string[];
  ipv4_count: number;
  ipv6_count: number;
  content_hash: string;
  created_at: number;
}

export interface Diff {
  id: number;
  target: string;
  new_snapshot_id: number;
  old_snapshot_id: number | null;
  added_v4: string[];
  removed_v4: string[];
  added_v6: string[];
  removed_v6: string[];
  has_changes: boolean;
  diff_hash: string;
  created_at: number;
}

export interface Ticket {
  id: number;
  target: string;
  diff_id: number;
  external_ticket_id: string | null;
  status: string;
  created_at: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface RunResult {
  targets_processed: number;
  diffs_found: number;
  tickets_created: number;
  errors: string[];
}
