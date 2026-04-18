import { useState } from 'react';
import { api, type PrefixResponse } from '../api';

export default function PrefixesPage() {
  const [target, setTarget] = useState('');
  const [result, setResult] = useState<PrefixResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'ipv4' | 'ipv6'>('ipv4');

  const handleFetch = () => {
    if (!target.trim()) return;
    setLoading(true);
    setError(null);
    api.getPrefixes(target.trim().toUpperCase())
      .then(setResult)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const prefixes = result
    ? (activeTab === 'ipv4' ? result.ipv4_prefixes : result.ipv6_prefixes)
    : [];

  return (
    <div className="p-6 max-w-4xl">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Prefixes</h2>
      <p className="text-sm text-gray-500 mb-6">Look up current prefixes for any target</p>

      <div className="flex gap-2 mb-6">
        <input
          type="text"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleFetch()}
          placeholder="AS15169 or AS-GOOGLE"
          className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={handleFetch}
          disabled={loading || !target.trim()}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? 'Fetching\u2026' : 'Fetch'}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">{error}</div>
      )}

      {result && (
        <div className="bg-white rounded-lg border border-gray-200">
          <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
            <div className="text-sm text-gray-600">
              Sources: <span className="font-medium">{result.sources_queried.join(', ')}</span>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setActiveTab('ipv4')}
                className={`text-sm px-3 py-1 rounded-md font-medium transition-colors ${activeTab === 'ipv4' ? 'bg-blue-50 text-blue-700' : 'text-gray-500 hover:text-gray-700'}`}
              >
                IPv4 ({result.ipv4_count})
              </button>
              <button
                onClick={() => setActiveTab('ipv6')}
                className={`text-sm px-3 py-1 rounded-md font-medium transition-colors ${activeTab === 'ipv6' ? 'bg-blue-50 text-blue-700' : 'text-gray-500 hover:text-gray-700'}`}
              >
                IPv6 ({result.ipv6_count})
              </button>
            </div>
          </div>
          <div className="p-4 max-h-96 overflow-y-auto">
            {prefixes.length === 0 ? (
              <p className="text-sm text-gray-400">No prefixes.</p>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-1">
                {prefixes.map((p) => (
                  <span key={p} className="font-mono text-xs text-gray-700 bg-gray-50 px-2 py-1 rounded">
                    {p}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
