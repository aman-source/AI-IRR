import { useEffect, useState } from 'react';
import { Target, GitCompareArrows, Ticket, Clock, Play, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { api, type OverviewStats, type RunResult } from '../api';
import PageHeader from '../components/PageHeader';

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon: React.ElementType;
  iconClass: string;
  iconBg: string;
}

function StatCard({ label, value, sub, icon: Icon, iconClass, iconBg }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 flex items-start gap-4">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${iconBg}`}>
        <Icon size={18} strokeWidth={1.75} className={iconClass} />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
        <p className="mt-1 text-2xl font-bold text-gray-900 leading-none">{value}</p>
        {sub && <p className="mt-1 text-xs text-gray-400 truncate">{sub}</p>}
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 flex items-start gap-4 animate-pulse">
      <div className="w-10 h-10 rounded-lg bg-gray-100 shrink-0" />
      <div className="flex-1">
        <div className="h-3 bg-gray-100 rounded w-20 mb-3" />
        <div className="h-7 bg-gray-100 rounded w-14" />
      </div>
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
      .then((result) => { setRunResult(result); loadStats(); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setRunning(false));
  };

  return (
    <div>
      <PageHeader
        title="Overview"
        description="BGP prefix monitoring status"
        action={
          <button
            onClick={handleRun}
            disabled={running}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            {running
              ? <><Loader2 size={14} className="animate-spin" /> Running…</>
              : <><Play size={14} /> Run Now</>}
          </button>
        }
      />

      <div className="px-8 py-6 max-w-5xl">
        {error && (
          <div className="mb-5 flex items-start gap-2.5 p-3.5 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <AlertCircle size={15} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        {runResult && (
          <div className="mb-5 flex items-start gap-2.5 p-3.5 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
            <CheckCircle2 size={15} className="mt-0.5 shrink-0" />
            <span>
              Run complete — {runResult.targets_processed} targets processed, {runResult.diffs_found} diff{runResult.diffs_found !== 1 ? 's' : ''} found.
              {runResult.errors.length > 0 && <span className="text-red-600 ml-1">{runResult.errors.length} error(s).</span>}
            </span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {loading ? (
            [...Array(4)].map((_, i) => <SkeletonCard key={i} />)
          ) : stats ? (
            <>
              <StatCard
                label="Targets"
                value={stats.total_targets}
                icon={Target}
                iconBg="bg-blue-50"
                iconClass="text-blue-600"
              />
              <StatCard
                label="Diffs (24h)"
                value={stats.recent_diffs}
                icon={GitCompareArrows}
                iconBg="bg-amber-50"
                iconClass="text-amber-600"
              />
              <StatCard
                label="Open Tickets"
                value={stats.open_tickets}
                icon={Ticket}
                iconBg="bg-violet-50"
                iconClass="text-violet-600"
              />
              <StatCard
                label="Last Run"
                value={stats.last_run_at ? formatTs(stats.last_run_at).split(',')[0] : '—'}
                sub={stats.last_run_at ? formatTs(stats.last_run_at).split(',')[1]?.trim() : undefined}
                icon={Clock}
                iconBg="bg-slate-50"
                iconClass="text-slate-500"
              />
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
