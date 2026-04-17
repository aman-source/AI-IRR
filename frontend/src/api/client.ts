import type {
  HealthResponse,
  OverviewStats,
  PaginatedResponse,
  PrefixResponse,
  RunResult,
  Snapshot,
  Diff,
  Ticket,
} from './types';

const BASE = '/api/v1';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  getTargets: () => request<string[]>(`${BASE}/targets`),

  getOverview: () => request<OverviewStats>(`${BASE}/overview`),

  getPrefixes: (target: string) =>
    request<PrefixResponse>(`${BASE}/prefixes/${encodeURIComponent(target)}`),

  triggerRun: () =>
    request<RunResult>(`${BASE}/run`, { method: 'POST' }),

  getSnapshots: (params: { page?: number; page_size?: number; target?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.page) q.set('page', String(params.page));
    if (params.page_size) q.set('page_size', String(params.page_size));
    if (params.target) q.set('target', params.target);
    return request<PaginatedResponse<Snapshot>>(`${BASE}/snapshots?${q}`);
  },

  getDiffs: (params: { page?: number; page_size?: number; target?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.page) q.set('page', String(params.page));
    if (params.page_size) q.set('page_size', String(params.page_size));
    if (params.target) q.set('target', params.target);
    return request<PaginatedResponse<Diff>>(`${BASE}/diffs?${q}`);
  },

  getTickets: (params: { page?: number; page_size?: number; target?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.page) q.set('page', String(params.page));
    if (params.page_size) q.set('page_size', String(params.page_size));
    if (params.target) q.set('target', params.target);
    return request<PaginatedResponse<Ticket>>(`${BASE}/tickets?${q}`);
  },
};
