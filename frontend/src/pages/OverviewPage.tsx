import { useEffect, useState } from 'react';
import { api, type OverviewStats, type RunResult } from '../api';

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <p className="text-sm font-medium text-gray-500">{label}</p>
      <p className="mt-1 text-3xl font-bold text-gray-900">{value}</p>
      {sub && <p className="mt-1 text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

function formatTs(ts: number | null): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

export default function OverviewPage() {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<RunResult | null>(null);

  const loadStats = () => {
    setLoading(true);
    setError(null);
    api.getOverview()
      .then(setStats)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadStats(); }, []);

  const handleRun = () => {
    setRunning(true);
    setRunResult(null);
    api.triggerRun()
      .then((result) => {
        setRunResult(result);
        loadStats(); // refresh stats after run
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setRunning(false));
  };

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Overview</h2>
          <p className="text-sm text-gray-500 mt-1">BGP prefix monitoring status</p>
        </div>
        <button
          onClick={handleRun}
          disabled={running}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {running ? 'Running…' : 'Run Now'}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}

      {runResult && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-md text-sm text-green-700">
          Run complete: {runResult.targets_processed} targets processed,{' '}
          {runResult.diffs_found} diffs found.
          {runResult.errors.length > 0 && (
            <span className="text-red-600"> {runResult.errors.length} error(s).</span>
          )}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-200 p-5 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-24 mb-3" />
              <div className="h-8 bg-gray-200 rounded w-16" />
            </div>
          ))}
        </div>
      ) : stats ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Targets" value={stats.total_targets} />
          <StatCard label="Diffs (24h)" value={stats.recent_diffs} />
          <StatCard label="Open Tickets" value={stats.open_tickets} />
          <StatCard
            label="Last Run"
            value={stats.last_run_at ? formatTs(stats.last_run_at).split(',')[0] : '—'}
            sub={stats.last_run_at ? formatTs(stats.last_run_at).split(',')[1]?.trim() : undefined}
          />
        </div>
      ) : null}
    </div>
  );
}
