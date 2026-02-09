import { useState, useEffect } from 'react';
import { fetchThreads, fetchStats } from '../api';
import SearchBar from './SearchBar';
import Stats from './Stats';
import ThreadCard from './ThreadCard';

export default function ThreadList() {
  const [threads, setThreads] = useState([]);
  const [stats, setStats] = useState(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([fetchThreads(100), fetchStats()])
      .then(([threadData, statsData]) => {
        setThreads(threadData.threads);
        setStats(statsData);
        setLoading(false);
      })
      .catch(err => {
        setError("Can't connect to server. Make sure the backend is running on port 8000.");
        setLoading(false);
      });
  }, []);

  const filtered = threads.filter(t => {
    if (!search) return true;
    const q = search.toLowerCase();
    const fields = [
      t.title,
      t.summary,
      ...(t.key_takeaways || []),
      ...(t.open_threads || []),
      ...(t.tags || []),
    ];
    return fields.some(f => f && f.toLowerCase().includes(q));
  });

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12 text-center text-gray-500">
        Loading...
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12 text-center text-red-500">
        {error}
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-gray-900">ContextHub</h1>
        <Stats stats={stats} />
      </div>

      <div className="mb-6">
        <SearchBar value={search} onChange={setSearch} />
      </div>

      {filtered.length === 0 ? (
        <div className="text-center text-gray-400 py-12">
          {search ? "No contexts match your search." : "No contexts yet. Push a conversation to get started."}
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map(thread => (
            <ThreadCard key={thread.id} thread={thread} />
          ))}
        </div>
      )}
    </div>
  );
}
