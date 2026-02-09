import { useState } from 'react';

export default function Stats({ stats }) {
  const [open, setOpen] = useState(false);

  if (!stats) return null;

  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(!open)}
        className="text-sm text-gray-500 hover:text-gray-700 cursor-pointer flex items-center gap-1"
      >
        Stats {open ? "\u25B2" : "\u25BC"}
      </button>
      {open && (
        <div className="mt-2 flex gap-6 text-sm text-gray-600">
          <div>
            <span className="font-medium text-gray-900">{stats.total_threads}</span> total contexts
          </div>
          <div>
            <span className="font-medium text-gray-900">{stats.threads_this_week}</span> this week
          </div>
          <div>
            <span className="font-medium text-gray-900">{stats.total_pulls}</span> pulls
          </div>
        </div>
      )}
    </div>
  );
}
