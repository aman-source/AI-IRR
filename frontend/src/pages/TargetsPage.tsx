import { useEffect, useState } from 'react';
import { api, type PrefixResponse } from '../api';

function TargetRow({ target }: { target: string }) {
  const [prefixes, setPrefixes] = useState<PrefixResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState(false);

  const fetchPrefixes = () => {
    setLoading(true);
    api.getPrefixes(target)
      .then((data) => { setPrefixes(data); setFetched(true); })
      .catch(() => { setFetched(true); })
      .finally(() => setLoading(false));
  };

  return (
    <tr className="border-t border-gray-100 hover:bg-gray-50">
      <td className="px-4 py-3 font-mono text-sm text-gray-900">{target}</td>
      <td className="px-4 py-3 text-sm text-gray-500">
        {fetched && prefixes ? prefixes.ipv4_count : '—'}
      </td>
      <td className="px-4 py-3 text-sm text-gray-500">
        {fetched && prefixes ? prefixes.ipv6_count : '—'}
      </td>
      <td className="px-4 py-3 text-sm text-gray-500">
        {fetched && prefixes ? prefixes.sources_queried.join(', ') : '—'}
      </td>
      <td className="px-4 py-3">
        <button
          onClick={fetchPrefixes}
          disabled={loading}
          className="text-xs px-2 py-1 bg-blue-50 text-blue-700 rounded hover:bg-blue-100 disabled:opacity-50 transition-colors"
        >
          {loading ? '…' : fetched ? 'Refresh' : 'Fetch'}
        </button>
      </td>
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
    <div className="p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Targets</h2>
      <p className="text-sm text-gray-500 mb-6">Monitored ASNs and AS-SETs</p>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-gray-400 animate-pulse">Loading…</p>
      ) : targets.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <p className="text-4xl mb-2">🌐</p>
          <p className="text-sm">No targets found. Add targets in config.yaml.</p>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-left">
            <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3">Target</th>
                <th className="px-4 py-3">IPv4 Prefixes</th>
                <th className="px-4 py-3">IPv6 Prefixes</th>
                <th className="px-4 py-3">IRR Sources</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {targets.map((t) => (
                <TargetRow key={t} target={t} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
