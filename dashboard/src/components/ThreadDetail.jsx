import { useState, useEffect, useMemo } from 'react';
import { useOutletContext, useParams } from 'react-router-dom';
import { fetchThread, fetchRawTranscript, fetchContext, recordPull, retryExtraction, updateThread } from '../api';
import { timeAgo } from '../utils/timeAgo';
import CopyButton from './CopyButton';
import MoveToFolderMenu from './MoveToFolderMenu';

const TYPE_META = {
  decision:   { label: 'Decision',   color: 'text-amber-700',   bg: 'bg-amber-50',   border: 'border-amber-200' },
  build:      { label: 'Build',      color: 'text-indigo-700',  bg: 'bg-indigo-50',  border: 'border-indigo-200' },
  research:   { label: 'Research',   color: 'text-sky-700',     bg: 'bg-sky-50',     border: 'border-sky-200' },
  brainstorm: { label: 'Brainstorm', color: 'text-pink-700',    bg: 'bg-pink-50',    border: 'border-pink-200' },
  debug:      { label: 'Debug',      color: 'text-rose-700',    bg: 'bg-rose-50',    border: 'border-rose-200' },
  planning:   { label: 'Planning',   color: 'text-violet-700',  bg: 'bg-violet-50',  border: 'border-violet-200' },
  learning:   { label: 'Learning',   color: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200' },
  writing:    { label: 'Writing',    color: 'text-cyan-700',    bg: 'bg-cyan-50',    border: 'border-cyan-200' },
  other:      { label: 'Other',      color: 'text-slate-700',   bg: 'bg-slate-100',  border: 'border-slate-200' },
};

function SectionCard({ title, children, accent }) {
  return (
    <section className="rounded-xl border border-line bg-white card-shadow overflow-hidden">
      <header className="px-5 pt-4 pb-2 flex items-center gap-2">
        {accent && <div className={`w-1 h-4 rounded-full ${accent}`} />}
        <h2 className="text-[11px] font-bold text-ink-500 uppercase tracking-[0.08em]">{title}</h2>
      </header>
      <div className="px-5 pb-5">{children}</div>
    </section>
  );
}

export default function ThreadDetail() {
  const { id } = useParams();
  const outletCtx = useOutletContext() || {};
  const allThreads = outletCtx.threads || [];
  const onThreadUpdated = outletCtx.onThreadUpdated;
  const folderNames = useMemo(() => {
    const set = new Set();
    for (const t of allThreads) if (t.folder) set.add(t.folder);
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [allThreads]);
  const [thread, setThread] = useState(null);
  const [raw, setRaw] = useState(null);
  const [showRaw, setShowRaw] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retrying, setRetrying] = useState(false);

  const moveToFolder = async (folder) => {
    const updated = await updateThread(id, { folder });
    setThread(updated);
    onThreadUpdated && onThreadUpdated(updated);
  };

  useEffect(() => {
    setThread(null);
    setRaw(null);
    setShowRaw(false);
    setError(null);
    setLoading(true);
    fetchThread(id)
      .then(data => { setThread(data); setLoading(false); })
      .catch(() => { setError('Failed to load this context.'); setLoading(false); });
  }, [id]);

  const handleCopyContext = async () => {
    const data = await fetchContext(id);
    await recordPull(id);
    return data.formatted_context;
  };

  const handleRetry = async () => {
    setRetrying(true);
    try {
      const updated = await retryExtraction(id);
      setThread(updated);
    } catch {
      setError('Retry failed. Please try again.');
    }
    setRetrying(false);
  };

  const handleShowRaw = async () => {
    if (!raw) {
      try {
        const data = await fetchRawTranscript(id);
        setRaw(data);
      } catch {
        setError('Failed to load raw transcript.');
        return;
      }
    }
    setShowRaw(!showRaw);
  };

  if (loading) {
    return <div className="px-10 py-12 text-center text-ink-400">Loading...</div>;
  }

  if (error && !thread) {
    return (
      <div className="px-10 py-12 text-center">
        <p className="text-rose-500">{error}</p>
      </div>
    );
  }

  const takeaways = thread.key_takeaways || [];
  const artifacts = thread.artifacts || [];
  const openThreads = thread.open_threads || [];
  const tags = thread.tags || [];
  const typeKey = thread.conversation_type && TYPE_META[thread.conversation_type] ? thread.conversation_type : 'other';
  const meta = TYPE_META[typeKey];

  return (
    <div className="max-w-4xl mx-auto px-8 py-8">
      {/* Hero */}
      <div className="mb-6">
        <div className="flex items-start justify-between gap-4 mb-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span className={`px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider rounded ${meta.bg} ${meta.color} border ${meta.border}`}>
                {meta.label}
              </span>
              <MoveToFolderMenu
                currentFolder={thread.folder ?? null}
                folders={folderNames}
                onSelect={moveToFolder}
                trigger={(open) => (
                  <button
                    type="button"
                    onClick={open}
                    className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] rounded border cursor-pointer transition-colors ${
                      thread.folder
                        ? 'bg-brand-50 text-brand-700 border-brand-200 hover:bg-brand-100'
                        : 'bg-white text-ink-500 border-line hover:border-brand-300 hover:text-brand-600'
                    }`}
                    title="Move to folder"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
                    </svg>
                    <span className="font-medium">{thread.folder || 'Unfiled'}</span>
                  </button>
                )}
              />
              <span className="text-[12px] text-ink-400">{thread.source}</span>
              <span className="text-ink-300">·</span>
              <span className="text-[12px] text-ink-400">{thread.message_count} messages</span>
              <span className="text-ink-300">·</span>
              <span className="text-[12px] text-ink-400">Pushed {timeAgo(thread.created_at)}</span>
            </div>
            <h1 className="text-[26px] font-semibold tracking-tight text-ink-900 leading-tight">
              {thread.title || 'Untitled'}
            </h1>
            {thread.source_url && (
              <a
                href={thread.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-2 text-[13px] text-brand-600 hover:text-brand-700 no-underline"
              >
                Original conversation
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </a>
            )}
          </div>
          <div className="shrink-0">
            <CopyButton getText={handleCopyContext} />
          </div>
        </div>
      </div>

      {thread.extraction_status === 'failed' && (
        <div className="mb-5 p-4 rounded-xl border border-rose-200 bg-rose-50">
          <p className="text-sm text-rose-700 mb-2">
            <span className="font-medium">Extraction failed.</span>{' '}
            {thread.extraction_error}
          </p>
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="px-3 py-1.5 text-sm bg-rose-600 text-white rounded-md hover:bg-rose-700 disabled:opacity-50 cursor-pointer"
          >
            {retrying ? 'Retrying...' : 'Retry Extraction'}
          </button>
        </div>
      )}

      <div className="space-y-4">
        {thread.summary && (
          <SectionCard title="Summary" accent="brand-gradient">
            <p className="text-[14px] text-ink-700 leading-relaxed">{thread.summary}</p>
          </SectionCard>
        )}

        {takeaways.length > 0 && (
          <SectionCard title="Key Takeaways" accent="bg-emerald-400">
            <ul className="space-y-2">
              {takeaways.map((t, i) => (
                <li key={i} className="flex items-start gap-2.5 text-[14px] text-ink-700">
                  <span className="mt-1 w-4 h-4 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center shrink-0">
                    <svg className="w-2.5 h-2.5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </span>
                  <span className="leading-relaxed">{t}</span>
                </li>
              ))}
            </ul>
          </SectionCard>
        )}

        {artifacts.length > 0 && (
          <SectionCard title={`Artifacts (${artifacts.length})`} accent="bg-indigo-400">
            <div className="space-y-3">
              {artifacts.map((a, i) => (
                <div key={i} className="rounded-lg border border-line overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-line">
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-ink-700 truncate">{a.description}</p>
                      {a.language && (
                        <p className="text-[11px] text-ink-400 uppercase tracking-wider">{a.language}</p>
                      )}
                    </div>
                    <CopyButton getText={a.content} label="Copy" className="text-[11px] !py-1 !px-2" />
                  </div>
                  <pre className="bg-slate-50/50 text-[12.5px] text-ink-900 overflow-x-auto p-3 leading-relaxed">
                    <code>{a.content}</code>
                  </pre>
                </div>
              ))}
            </div>
          </SectionCard>
        )}

        {openThreads.length > 0 && (
          <SectionCard title="Still Open" accent="bg-amber-400">
            <ul className="space-y-2">
              {openThreads.map((q, i) => (
                <li key={i} className="flex items-start gap-2.5 text-[14px] text-ink-700">
                  <span className="mt-0.5 w-5 h-5 rounded-full bg-amber-50 border border-amber-200 text-amber-700 text-[12px] font-semibold flex items-center justify-center shrink-0">?</span>
                  <span className="leading-relaxed">{q}</span>
                </li>
              ))}
            </ul>
          </SectionCard>
        )}

        {tags.length > 0 && (
          <SectionCard title="Tags" accent="bg-violet-400">
            <div className="flex flex-wrap gap-1.5">
              {tags.map((tag, i) => (
                <span
                  key={i}
                  className="px-2.5 py-1 text-[12px] bg-brand-50 text-brand-700 border border-brand-200 rounded-full font-medium"
                >
                  {tag}
                </span>
              ))}
            </div>
          </SectionCard>
        )}

        <div className="rounded-xl border border-line bg-white card-shadow">
          <button
            onClick={handleShowRaw}
            className="w-full flex items-center justify-between px-5 py-3 text-[13px] font-medium text-ink-700 hover:bg-slate-50 cursor-pointer rounded-xl"
          >
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4 text-ink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              Raw Transcript
            </span>
            <svg className={`w-4 h-4 text-ink-400 transition-transform ${showRaw ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {showRaw && raw && (
            <div className="px-5 pb-5 pt-1 space-y-3 max-h-[60vh] overflow-y-auto border-t border-line">
              {raw.messages && raw.messages.map((msg, i) => (
                <div key={i} className="rounded-lg bg-slate-50 border border-line p-3">
                  <p className={`text-[10px] font-bold uppercase tracking-wider mb-1.5 ${msg.role === 'user' ? 'text-brand-600' : 'text-ink-500'}`}>
                    {msg.role}
                  </p>
                  <p className="text-[13px] text-ink-700 whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
