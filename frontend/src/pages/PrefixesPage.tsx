import { useState } from 'react';
import { Search, Loader2, AlertCircle } from 'lucide-react';
import { api, type PrefixResponse } from '../api';
import PageHeader from '../components/PageHeader';

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
      .then((r) => { setResult(r); setActiveTab('ipv4'); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const prefixes = result ? (activeTab === 'ipv4' ? result.ipv4_prefixes : result.ipv6_prefixes) : [];

  return (
    <div>
      <PageHeader title="Prefixes" description="Look up current IRR prefixes for any target" />
      <div className="px-8 py-6 max-w-4xl">
        {/* Search bar */}
        <div className="flex gap-2 mb-6">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input
              type="text"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleFetch()}
              placeholder="AS15169 or AS-GOOGLE"
              className="w-full pl-9 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
            />
          </div>
          <button
            onClick={handleFetch}
            disabled={loading || !target.trim()}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            {loading ? 'Fetching…' : 'Fetch'}
          </button>
        </div>

        {error && (
          <div className="mb-5 flex items-start gap-2.5 p-3.5 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <AlertCircle size={15} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        {result && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            {/* Header row */}
            <div className="px-5 py-3.5 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span className="font-medium text-gray-700">{result.target}</span>
                <span className="text-gray-300">·</span>
                <span>Sources:</span>
                {result.sources_queried.map((s) => (
                  <span key={s} className="px-1.5 py-0.5 bg-white border border-gray-200 text-gray-600 text-xs rounded font-mono">{s}</span>
                ))}
              </div>
              {/* Tabs */}
              <div className="flex bg-gray-100 rounded-lg p-0.5">
                {(['ipv4', 'ipv6'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                      activeTab === tab
                        ? 'bg-white text-gray-900 shadow-sm'
                        : 'text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    {tab === 'ipv4' ? 'IPv4' : 'IPv6'}
                    <span className="ml-1.5 text-gray-400">
                      {tab === 'ipv4' ? result.ipv4_count : result.ipv6_count}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="p-5 max-h-[480px] overflow-y-auto">
              {prefixes.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-6">No {activeTab.toUpperCase()} prefixes found.</p>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 gap-1.5">
                  {prefixes.map((p) => (
                    <span key={p} className="font-mono text-xs text-gray-700 bg-gray-50 border border-gray-100 px-2.5 py-1.5 rounded-md">
                      {p}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
