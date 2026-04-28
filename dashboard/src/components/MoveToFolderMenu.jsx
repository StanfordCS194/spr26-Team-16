import { useEffect, useRef, useState } from 'react';

/**
 * Compact "move to folder" picker. Lists existing folders, lets the user
 * create a new one, and unfile.
 *
 * Props:
 *   currentFolder: string | null
 *   folders:       string[]   (known folder names from other threads)
 *   onSelect:      (folder: string | null) => Promise<void> | void
 *   trigger:       (open: () => void) => ReactNode
 */
export default function MoveToFolderMenu({ currentFolder, folders, onSelect, trigger }) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false);
        setCreating(false);
        setNewName('');
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const choose = async (name) => {
    setOpen(false);
    setCreating(false);
    setNewName('');
    await onSelect(name);
  };

  const submitNew = async (e) => {
    e.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed) return;
    await choose(trimmed);
  };

  return (
    <div ref={wrapRef} className="relative inline-block">
      {trigger(() => setOpen(o => !o))}
      {open && (
        <div className="absolute right-0 top-full mt-1 z-30 w-56 rounded-lg border border-line bg-white card-shadow-lg py-1">
          <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-400">
            Move to folder
          </div>
          <button
            type="button"
            onClick={() => choose(null)}
            className={`w-full text-left px-3 py-1.5 text-[13px] hover:bg-slate-50 cursor-pointer flex items-center gap-2 ${
              currentFolder == null ? 'text-brand-700 font-medium' : 'text-ink-700'
            }`}
          >
            <svg className="w-3.5 h-3.5 text-ink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
            Unfiled
          </button>
          {folders.length > 0 && <div className="my-1 border-t border-line" />}
          <div className="max-h-52 overflow-y-auto">
            {folders.map(name => (
              <button
                key={name}
                type="button"
                onClick={() => choose(name)}
                className={`w-full text-left px-3 py-1.5 text-[13px] hover:bg-slate-50 cursor-pointer flex items-center gap-2 ${
                  currentFolder === name ? 'text-brand-700 font-medium' : 'text-ink-700'
                }`}
              >
                <svg className="w-3.5 h-3.5 text-ink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                <span className="truncate">{name}</span>
                {currentFolder === name && (
                  <svg className="ml-auto w-3.5 h-3.5 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </button>
            ))}
          </div>
          <div className="my-1 border-t border-line" />
          {creating ? (
            <form onSubmit={submitNew} className="px-2 py-1.5">
              <input
                autoFocus
                type="text"
                value={newName}
                placeholder="Folder name"
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    setCreating(false);
                    setNewName('');
                  }
                }}
                className="w-full px-2 py-1 border border-line rounded text-[13px] focus:outline-none focus:ring-2 focus:ring-brand-300 focus:border-brand-300"
              />
              <div className="flex gap-1.5 mt-1.5">
                <button
                  type="submit"
                  disabled={!newName.trim()}
                  className="flex-1 px-2 py-1 text-[12px] font-medium brand-gradient text-white rounded disabled:opacity-50 cursor-pointer"
                >
                  Create
                </button>
                <button
                  type="button"
                  onClick={() => { setCreating(false); setNewName(''); }}
                  className="px-2 py-1 text-[12px] text-ink-500 hover:text-ink-700 cursor-pointer"
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="w-full text-left px-3 py-1.5 text-[13px] text-brand-600 hover:bg-brand-50 cursor-pointer flex items-center gap-2 font-medium"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New folder…
            </button>
          )}
        </div>
      )}
    </div>
  );
}
