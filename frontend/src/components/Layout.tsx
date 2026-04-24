import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, Target, Globe, GitCompareArrows, Ticket, Radio } from 'lucide-react';

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/targets', label: 'Targets', icon: Target },
  { to: '/prefixes', label: 'Prefixes', icon: Globe },
  { to: '/diffs', label: 'Diffs', icon: GitCompareArrows },
  { to: '/tickets', label: 'Tickets', icon: Ticket },
];

export default function Layout() {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <aside className="w-60 bg-slate-900 flex flex-col shrink-0">
        {/* Logo */}
        <div className="px-5 py-5 flex items-center gap-3 border-b border-slate-800">
          <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center shrink-0">
            <Radio size={16} className="text-white" strokeWidth={2} />
          </div>
          <div>
            <p className="text-sm font-semibold text-white leading-none">AI-IRR</p>
            <p className="text-xs text-slate-400 mt-0.5">BGP Prefix Monitor</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
                }`
              }
            >
              <Icon size={15} strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-5 py-4 border-t border-slate-800">
          <p className="text-xs text-slate-600">v1.0.0</p>
        </div>
      </aside>

      <main className="flex-1 overflow-auto min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
