import { useEffect, useState } from 'react';
import { RefreshCw, ServerOff, AlertCircle, Loader2 } from 'lucide-react';
import { api, type Snapshot } from '../api';
import PageHeader from '../components/PageHeader';

function TargetRow({ target }: { target: string }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    api.getSnapshots({ target, page: 1, page_size: 1 })
      .then((res) => setSnapshot(res.items[0] ?? null))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [target]);

  const handleRefresh = () => {
    setRefreshing(true);
    api.getPrefixes(target)
      .then(() => api.getSnapshots({ target, page: 1, page_size: 1 }))
      .then((res) => setSnapshot(res.items[0] ?? null))
      .catch(() => {})
      .finally(() => setRefreshing(false));
  };

  return (
    <tr className="group border-t border-gray-100 hover:bg-gray-50 transition-colors">
      <td className="px-6 py-3.5 font-mono text-sm font-medium text-gray-900">{target}</td>
      <td className="px-6 py-3.5 text-sm tabular-nums text-gray-600">
        {loading ? <Loader2 size={13} className="animate-spin text-gray-300" /> : snapshot ? snapshot.ipv4_count.toLocaleString() : <span className="text-gray-300">—</span>}
      </td>
      <td className="px-6 py-3.5 text-sm tabular-nums text-gray-600">
        {loading ? <Loader2 size={13} className="animate-spin text-gray-300" /> : snapshot ? snapshot.ipv6_count.toLocaleString() : <span className="text-gray-300">—</span>}
      </td>
      <td className="px-6 py-3.5 text-sm text-gray-500">
        {loading ? (
          <Loader2 size={13} className="animate-spin text-gray-300" />
        ) : snapshot?.irr_sources?.length ? (
          snapshot.irr_sources.map((s) => (
            <span key={s} className="inline-block mr-1 mb-0.5 px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded font-mono">
              {s}
            </span>
          ))
        ) : <span className="text-gray-300">—</span>}
      </td>
      <td className="px-6 py-3.5 text-right">
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 text-gray-600 border border-gray-200 rounded-md hover:bg-gray-50 hover:border-gray-300 disabled:opacity-50 transition-colors"
          title="Fetch fresh data from IRR (requires bgpq4)"
        >
          <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
          {refreshing ? 'Fetching' : 'Refresh'}
        </button>
      </td>
    </tr>
  );
}

function SkeletonRow() {
  return (
    <tr className="border-t border-gray-100 animate-pulse">
      {[40, 20, 20, 48, 16].map((w, i) => (
        <td key={i} className="px-6 py-3.5">
          <div className={`h-4 bg-gray-100 rounded w-${w}`} />
        </td>
      ))}
    </tr>
  );
}

export default function TargetsPage() {
  const [targets, setTargets] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getTargets()
      .then(setTargets)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader title="Targets" description="Monitored ASNs and AS-SETs" />
      <div className="px-8 py-6">
        {error && (
          <div className="mb-5 flex items-start gap-2.5 p-3.5 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <AlertCircle size={15} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Target</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">IPv4</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">IPv6</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">IRR Sources</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                [...Array(4)].map((_, i) => <SkeletonRow key={i} />)
              ) : targets.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-16 text-center">
                    <ServerOff size={32} strokeWidth={1.5} className="mx-auto mb-3 text-gray-200" />
                    <p className="text-sm text-gray-400">No targets configured. Add targets in <code className="font-mono bg-gray-100 px-1 rounded">config.yaml</code>.</p>
                  </td>
                </tr>
              ) : (
                targets.map((t) => <TargetRow key={t} target={t} />)
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
