import { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp, GitCompareArrows, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import { api, type Diff, type PaginatedResponse } from '../api';
import PageHeader from '../components/PageHeader';

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function DiffRow({ diff }: { diff: Diff }) {
  const [expanded, setExpanded] = useState(false);
  const added = diff.added_v4.length + diff.added_v6.length;
  const removed = diff.removed_v4.length + diff.removed_v6.length;

  return (
    <>
      <tr
        className="border-t border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <td className="px-6 py-3.5 font-mono text-sm font-medium text-gray-900">{diff.target}</td>
        <td className="px-6 py-3.5">
          {diff.has_changes ? (
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-amber-50 text-amber-700 border border-amber-100">
              Changed
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium bg-gray-50 text-gray-400 border border-gray-100">
              No change
            </span>
          )}
        </td>
        <td className="px-6 py-3.5 text-sm tabular-nums">
          {added > 0
            ? <span className="text-emerald-600 font-medium">+{added}</span>
            : <span className="text-gray-300">—</span>}
        </td>
        <td className="px-6 py-3.5 text-sm tabular-nums">
          {removed > 0
            ? <span className="text-red-500 font-medium">-{removed}</span>
            : <span className="text-gray-300">—</span>}
        </td>
        <td className="px-6 py-3.5 text-xs text-gray-400">{formatTs(diff.created_at)}</td>
        <td className="px-6 py-3.5 text-gray-300">
          {diff.has_changes
            ? expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />
            : null}
        </td>
      </tr>
      {expanded && diff.has_changes && (
        <tr className="bg-slate-50">
          <td colSpan={6} className="px-8 py-4 border-t border-gray-100">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-xs font-mono">
              {added > 0 && (
                <div>
                  <p className="text-emerald-700 font-semibold text-xs uppercase tracking-wide mb-2 font-sans">Added ({added})</p>
                  <div className="space-y-0.5 max-h-48 overflow-y-auto">
                    {[...diff.added_v4, ...diff.added_v6].map((p) => (
                      <div key={p} className="text-emerald-700 bg-emerald-50 rounded px-2 py-0.5">+ {p}</div>
                    ))}
                  </div>
                </div>
              )}
              {removed > 0 && (
                <div>
                  <p className="text-red-600 font-semibold text-xs uppercase tracking-wide mb-2 font-sans">Removed ({removed})</p>
                  <div className="space-y-0.5 max-h-48 overflow-y-auto">
                    {[...diff.removed_v4, ...diff.removed_v6].map((p) => (
                      <div key={p} className="text-red-600 bg-red-50 rounded px-2 py-0.5">- {p}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function SkeletonRow() {
  return (
    <tr className="border-t border-gray-100 animate-pulse">
      {[32, 24, 12, 12, 28, 8].map((w, i) => (
        <td key={i} className="px-6 py-3.5">
          <div className={`h-4 bg-gray-100 rounded w-${w}`} />
        </td>
      ))}
    </tr>
  );
}

export default function DiffsPage() {
  const [data, setData] = useState<PaginatedResponse<Diff> | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.getDiffs({ page, page_size: 25 })
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [page]);

  return (
    <div>
      <PageHeader title="Diffs" description="Prefix change history across all targets" />
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
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Added</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Removed</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Time</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                [...Array(6)].map((_, i) => <SkeletonRow key={i} />)
              ) : !data || data.items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center">
                    <GitCompareArrows size={32} strokeWidth={1.5} className="mx-auto mb-3 text-gray-200" />
                    <p className="text-sm text-gray-400">No diffs yet. Run a fetch to detect changes.</p>
                  </td>
                </tr>
              ) : (
                data.items.map((d) => <DiffRow key={d.id} diff={d} />)
              )}
            </tbody>
          </table>
        </div>

        {data && data.pages > 1 && (
          <div className="flex items-center justify-between mt-4 text-sm text-gray-500">
            <span>{data.total.toLocaleString()} total · page {data.page} of {data.pages}</span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 border border-gray-200 rounded-md hover:bg-gray-50 disabled:opacity-40 transition-colors"
              >
                <ChevronLeft size={14} />
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= data.pages}
                className="p-1.5 border border-gray-200 rounded-md hover:bg-gray-50 disabled:opacity-40 transition-colors"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
