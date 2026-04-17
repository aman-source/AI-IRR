import { useEffect, useState } from 'react';
import { api, type Diff, type PaginatedResponse } from '../api';

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

function DiffRow({ diff }: { diff: Diff }) {
  const [expanded, setExpanded] = useState(false);
  const totalChanges = diff.added_v4.length + diff.removed_v4.length + diff.added_v6.length + diff.removed_v6.length;

  return (
    <>
      <tr
        className="border-t border-gray-100 hover:bg-gray-50 cursor-pointer"
        onClick={() => setExpanded((e) => !e)}
      >
        <td className="px-4 py-3 font-mono text-sm text-gray-900">{diff.target}</td>
        <td className="px-4 py-3 text-sm">
          {diff.has_changes ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700">
              Changed ({totalChanges})
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
              No change
            </span>
          )}
        </td>
        <td className="px-4 py-3 text-sm text-green-600">+{diff.added_v4.length + diff.added_v6.length}</td>
        <td className="px-4 py-3 text-sm text-red-600">-{diff.removed_v4.length + diff.removed_v6.length}</td>
        <td className="px-4 py-3 text-xs text-gray-400">{formatTs(diff.created_at)}</td>
        <td className="px-4 py-3 text-xs text-gray-300">{expanded ? '\u25b2' : '\u25bc'}</td>
      </tr>
      {expanded && diff.has_changes && (
        <tr className="bg-gray-50">
          <td colSpan={6} className="px-6 py-3">
            <div className="grid grid-cols-2 gap-4 text-xs font-mono">
              {diff.added_v4.length + diff.added_v6.length > 0 && (
                <div>
                  <p className="text-green-700 font-semibold mb-1">Added</p>
                  {[...diff.added_v4, ...diff.added_v6].map((p) => (
                    <div key={p} className="text-green-600">+ {p}</div>
                  ))}
                </div>
              )}
              {diff.removed_v4.length + diff.removed_v6.length > 0 && (
                <div>
                  <p className="text-red-700 font-semibold mb-1">Removed</p>
                  {[...diff.removed_v4, ...diff.removed_v6].map((p) => (
                    <div key={p} className="text-red-600">- {p}</div>
                  ))}
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
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
    <div className="p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Diffs</h2>
      <p className="text-sm text-gray-500 mb-6">Prefix change history</p>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">{error}</div>
      )}

      {loading ? (
        <p className="text-sm text-gray-400 animate-pulse">Loading\u2026</p>
      ) : data && data.items.length > 0 ? (
        <>
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden mb-4">
            <table className="w-full text-left">
              <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3">Target</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Added</th>
                  <th className="px-4 py-3">Removed</th>
                  <th className="px-4 py-3">Time</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((d) => <DiffRow key={d.id} diff={d} />)}
              </tbody>
            </table>
          </div>
          {data.pages > 1 && (
            <div className="flex items-center justify-between text-sm text-gray-500">
              <span>Page {data.page} of {data.pages} ({data.total} total)</span>
              <div className="flex gap-2">
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 border rounded hover:bg-gray-50 disabled:opacity-40">Previous</button>
                <button onClick={() => setPage((p) => p + 1)} disabled={page >= data.pages} className="px-3 py-1 border rounded hover:bg-gray-50 disabled:opacity-40">Next</button>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-12 text-gray-400">
          <p className="text-4xl mb-2">&#x1F500;</p>
          <p className="text-sm">No diffs yet. Run a fetch to detect changes.</p>
        </div>
      )}
    </div>
  );
}
