import { useEffect, useState } from 'react';
import { api, type Ticket, type PaginatedResponse } from '../api';

const STATUS_COLORS: Record<string, string> = {
  submitted: 'bg-green-50 text-green-700',
  pending: 'bg-yellow-50 text-yellow-700',
  closed: 'bg-gray-100 text-gray-500',
};

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export default function TicketsPage() {
  const [data, setData] = useState<PaginatedResponse<Ticket> | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.getTickets({ page, page_size: 25 })
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [page]);

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-gray-900 mb-1">Tickets</h2>
      <p className="text-sm text-gray-500 mb-6">Ticketing history for prefix changes</p>

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
                  <th className="px-4 py-3">Ticket ID</th>
                  <th className="px-4 py-3">Target</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Diff ID</th>
                  <th className="px-4 py-3">Created</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((t) => (
                  <tr key={t.id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-sm text-gray-900">
                      {t.external_ticket_id ?? <span className="text-gray-400">\u2014</span>}
                    </td>
                    <td className="px-4 py-3 font-mono text-sm text-gray-900">{t.target}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[t.status] ?? 'bg-gray-100 text-gray-600'}`}>
                        {t.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{t.diff_id}</td>
                    <td className="px-4 py-3 text-xs text-gray-400">{formatTs(t.created_at)}</td>
                  </tr>
                ))}
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
          <p className="text-4xl mb-2">&#x1F3AB;</p>
          <p className="text-sm">No tickets yet.</p>
        </div>
      )}
    </div>
  );
}
