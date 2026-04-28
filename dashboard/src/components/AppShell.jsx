import { useCallback, useEffect, useState } from 'react';
import { Outlet, Link } from 'react-router-dom';
import { fetchThreads, fetchStats } from '../api';
import Sidebar from './Sidebar';
import Stats from './Stats';

export default function AppShell() {
  const [threads, setThreads] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadData = () => {
    setLoading(true);
    Promise.all([fetchThreads(100), fetchStats()])
      .then(([t, s]) => {
        setThreads(t.threads);
        setStats(s);
        setError(null);
        setLoading(false);
      })
      .catch(() => {
        setError("Can't connect to server. Make sure the backend is running on port 8001.");
        setLoading(false);
      });
  };

  useEffect(() => { loadData(); }, []);

  // Update a single thread in-place (used after PATCH responses) so the
  // sidebar reflects folder changes without a full reload.
  const replaceThread = useCallback((updated) => {
    setThreads(prev => prev.map(t => (t.id === updated.id ? { ...t, ...updated } : t)));
  }, []);

  return (
    <div className="h-screen flex flex-col bg-canvas">
      <header className="flex items-center justify-between px-6 h-14 bg-white border-b border-line">
        <Link to="/" className="flex items-center gap-2.5 no-underline group">
          <img
            src="/logo.png"
            alt="ContextHub"
            className="w-9 h-9 rounded-lg shadow-sm shrink-0 object-contain bg-white"
          />
          <div className="leading-tight">
            <div className="text-[15px] font-semibold brand-text tracking-tight">ContextHub</div>
            <div className="text-[10px] text-ink-500 uppercase tracking-wider">Conversation Library</div>
          </div>
        </Link>
        <div className="flex items-center gap-4">
          <Stats stats={stats} />
          <button
            onClick={loadData}
            className="text-xs font-medium text-ink-500 hover:text-brand-600 transition-colors cursor-pointer flex items-center gap-1.5"
            title="Refresh"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        <Sidebar
          threads={threads}
          loading={loading}
          error={error}
          onThreadUpdated={replaceThread}
        />
        <main className="flex-1 overflow-y-auto">
          <Outlet context={{ threads, refresh: loadData, onThreadUpdated: replaceThread }} />
        </main>
      </div>
    </div>
  );
}
