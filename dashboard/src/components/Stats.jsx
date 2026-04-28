import { useState } from 'react';

export default function Stats({ stats }) {
  const [open, setOpen] = useState(false);

  if (!stats) return null;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="text-xs font-medium text-ink-500 hover:text-brand-600 transition-colors cursor-pointer flex items-center gap-1.5"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        Stats {open ? "▲" : "▼"}
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-2 z-20 w-64 rounded-xl border border-line bg-white card-shadow-lg p-4">
          <div className="grid grid-cols-3 gap-3 text-center">
            <div>
              <div className="text-[18px] font-semibold text-ink-900">{stats.total_threads}</div>
              <div className="text-[10px] uppercase tracking-wider text-ink-400 mt-0.5">Total</div>
            </div>
            <div>
              <div className="text-[18px] font-semibold brand-text">{stats.threads_this_week}</div>
              <div className="text-[10px] uppercase tracking-wider text-ink-400 mt-0.5">This week</div>
            </div>
            <div>
              <div className="text-[18px] font-semibold text-ink-900">{stats.total_pulls}</div>
              <div className="text-[10px] uppercase tracking-wider text-ink-400 mt-0.5">Pulls</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
