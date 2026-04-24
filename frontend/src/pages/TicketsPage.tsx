import { useEffect, useState } from 'react';
import { TicketX, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import { api, type Ticket, type PaginatedResponse } from '../api';
import PageHeader from '../components/PageHeader';

const STATUS_CONFIG: Record<string, { label: string; dot: string; text: string; bg: string }> = {
  submitted: { label: 'Submitted', dot: 'bg-emerald-400', text: 'text-emerald-700', bg: 'bg-emerald-50 border-emerald-100' },
  pending:   { label: 'Pending',   dot: 'bg-amber-400',   text: 'text-amber-700',   bg: 'bg-amber-50 border-amber-100'   },
  closed:    { label: 'Closed',    dot: 'bg-gray-300',    text: 'text-gray-500',    bg: 'bg-gray-50 border-gray-100'     },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, dot: 'bg-gray-300', text: 'text-gray-600', bg: 'bg-gray-50 border-gray-100' };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${cfg.bg} ${cfg.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function SkeletonRow() {
  return (
    <tr className="border-t border-gray-100 animate-pulse">
      {[36, 24, 20, 12, 24].map((w, i) => (
        <td key={i} className="px-6 py-3.5">
          <div className={`h-4 bg-gray-100 rounded w-${w}`} />
        </td>
      ))}
    </tr>
  );
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
    <div>
      <PageHeader title="Tickets" description="Ticketing history for prefix changes" />
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
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Ticket ID</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Target</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Diff</th>
                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Created</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                [...Array(5)].map((_, i) => <SkeletonRow key={i} />)
              ) : !data || data.items.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-16 text-center">
                    <TicketX size={32} strokeWidth={1.5} className="mx-auto mb-3 text-gray-200" />
                    <p className="text-sm text-gray-400">No tickets yet.</p>
                  </td>
                </tr>
              ) : (
                data.items.map((t) => (
                  <tr key={t.id} className="border-t border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-3.5 font-mono text-sm text-gray-900">
                      {t.external_ticket_id ?? <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-6 py-3.5 font-mono text-sm font-medium text-gray-900">{t.target}</td>
                    <td className="px-6 py-3.5">
                      <StatusBadge status={t.status} />
                    </td>
                    <td className="px-6 py-3.5 text-sm text-gray-400 tabular-nums">#{t.diff_id}</td>
                    <td className="px-6 py-3.5 text-xs text-gray-400">{formatTs(t.created_at)}</td>
                  </tr>
                ))
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
