import { useMemo, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { timeAgo } from '../utils/timeAgo';
import { updateThread } from '../api';
import SearchBar from './SearchBar';
import MoveToFolderMenu from './MoveToFolderMenu';

const UNFILED = '__unfiled__';

function FolderChevron({ open }) {
  return (
    <svg className={`w-3 h-3 transition-transform ${open ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
    </svg>
  );
}

function ThreadRow({ thread, folderNames, onMoved }) {
  const [busy, setBusy] = useState(false);

  const move = async (folder) => {
    if ((thread.folder ?? null) === (folder ?? null)) return;
    setBusy(true);
    try {
      const updated = await updateThread(thread.id, { folder });
      onMoved(updated);
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="group relative">
      <NavLink
        to={`/thread/${thread.id}`}
        className={({ isActive }) =>
          `block px-3 py-2.5 my-0.5 rounded-lg transition-colors no-underline border ${
            isActive
              ? 'bg-brand-50 border-brand-200 text-ink-900'
              : 'border-transparent hover:bg-slate-50 text-ink-700'
          }`
        }
      >
        {({ isActive }) => (
          <div className="flex items-start gap-2">
            <div className={`w-1.5 h-1.5 mt-1.5 rounded-full shrink-0 ${
              thread.extraction_status === 'failed' ? 'bg-rose-400'
              : thread.extraction_status === 'processing' || thread.extraction_status === 'pending' ? 'bg-amber-400'
              : isActive ? 'bg-brand-500' : 'bg-ink-300'
            }`} />
            <div className="min-w-0 flex-1 pr-5">
              <p className="text-[13px] font-medium leading-snug truncate">
                {thread.title || (thread.extraction_status !== 'done' ? 'Extracting context...' : 'Untitled')}
              </p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-[11px] text-ink-400">{timeAgo(thread.created_at)}</span>
                {thread.message_count != null && (
                  <>
                    <span className="text-ink-300">·</span>
                    <span className="text-[11px] text-ink-400">{thread.message_count} msgs</span>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </NavLink>
      <div className="absolute right-2 top-1.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
        <MoveToFolderMenu
          currentFolder={thread.folder ?? null}
          folders={folderNames}
          onSelect={move}
          trigger={(open) => (
            <button
              type="button"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); open(); }}
              disabled={busy}
              title="Move to folder"
              className="w-6 h-6 rounded-md bg-white border border-line text-ink-500 hover:text-brand-600 hover:border-brand-300 cursor-pointer flex items-center justify-center"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h.01M12 12h.01M19 12h.01" />
              </svg>
            </button>
          )}
        />
      </div>
    </li>
  );
}

export default function Sidebar({ threads, loading, error, onThreadUpdated }) {
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState({});

  const filtered = useMemo(() => {
    if (!search) return threads;
    const q = search.toLowerCase();
    return threads.filter(t => {
      const fields = [t.title, t.summary, t.folder, ...(t.key_takeaways || []), ...(t.open_threads || []), ...(t.tags || [])];
      return fields.some(f => f && f.toLowerCase().includes(q));
    });
  }, [threads, search]);

  // Group filtered threads by folder. Existing folders come from ALL threads
  // (so an empty folder still shows up after every thread leaves it… well, in
  // this design it won't, since folder lives on the thread). For move-target
  // listings we still derive from all threads.
  const allFolderNames = useMemo(() => {
    const set = new Set();
    for (const t of threads) if (t.folder) set.add(t.folder);
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [threads]);

  const groupedKeys = useMemo(() => {
    const set = new Set();
    let hasUnfiled = false;
    for (const t of filtered) {
      if (t.folder) set.add(t.folder);
      else hasUnfiled = true;
    }
    const named = Array.from(set).sort((a, b) => a.localeCompare(b));
    return hasUnfiled ? [...named, UNFILED] : named;
  }, [filtered]);

  const groupedItems = useMemo(() => {
    const map = {};
    for (const t of filtered) {
      const key = t.folder || UNFILED;
      if (!map[key]) map[key] = [];
      map[key].push(t);
    }
    return map;
  }, [filtered]);

  const toggle = (key) => setCollapsed(c => ({ ...c, [key]: !c[key] }));
  const totalShown = filtered.length;
  const hasFolders = allFolderNames.length > 0;

  return (
    <aside className="w-80 shrink-0 bg-white border-r border-line flex flex-col">
      <div className="p-4 border-b border-line">
        <SearchBar value={search} onChange={setSearch} />
        <div className="mt-3 text-[11px] text-ink-400 uppercase tracking-wider font-medium">
          {loading
            ? 'Loading…'
            : search
            ? `${totalShown} match${totalShown === 1 ? '' : 'es'}`
            : `${threads.length} conversation${threads.length === 1 ? '' : 's'}`}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {loading ? (
          <div className="px-4 py-8 text-center text-sm text-ink-400">Loading...</div>
        ) : error ? (
          <div className="px-4 py-8 text-center text-sm text-rose-500">{error}</div>
        ) : threads.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <div className="w-10 h-10 mx-auto rounded-full bg-brand-50 flex items-center justify-center mb-3">
              <svg className="w-5 h-5 text-brand-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <p className="text-sm text-ink-500 px-4">No contexts yet. Push a conversation to get started.</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-ink-400">No contexts match your search.</div>
        ) : !hasFolders ? (
          // Flat list: no folders exist yet, behave like before.
          <ul className="px-1.5">
            {filtered.map(t => (
              <ThreadRow
                key={t.id}
                thread={t}
                folderNames={allFolderNames}
                onMoved={onThreadUpdated}
              />
            ))}
          </ul>
        ) : (
          // Grouped by folder
          groupedKeys.map(key => {
            const items = groupedItems[key] || [];
            const isOpen = !collapsed[key];
            const isUnfiled = key === UNFILED;
            return (
              <div key={key} className="mb-1">
                <button
                  type="button"
                  onClick={() => toggle(key)}
                  className="w-full flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold text-ink-700 hover:bg-slate-50 cursor-pointer"
                >
                  <span className="text-ink-400"><FolderChevron open={isOpen} /></span>
                  <svg className={`w-3.5 h-3.5 ${isUnfiled ? 'text-ink-400' : 'text-brand-500'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    {isUnfiled ? (
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                    ) : (
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
                    )}
                  </svg>
                  <span className={`truncate ${isUnfiled ? 'text-ink-500 italic' : ''}`}>
                    {isUnfiled ? 'Unfiled' : key}
                  </span>
                  <span className="ml-auto text-[11px] text-ink-400 font-medium">{items.length}</span>
                </button>
                {isOpen && (
                  <ul className="px-1.5">
                    {items.map(t => (
                      <ThreadRow
                        key={t.id}
                        thread={t}
                        folderNames={allFolderNames}
                        onMoved={onThreadUpdated}
                      />
                    ))}
                  </ul>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
