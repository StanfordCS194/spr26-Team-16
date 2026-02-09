import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { fetchThread, fetchRawTranscript, fetchContext, recordPull, retryExtraction } from '../api';
import { timeAgo } from '../utils/timeAgo';
import CopyButton from './CopyButton';

const TYPE_LABELS = {
  decision: "Decision",
  build: "Build",
  research: "Research",
  brainstorm: "Brainstorm",
  debug: "Debug",
  planning: "Planning",
  learning: "Learning",
  writing: "Writing",
  other: "Other",
};

export default function ThreadDetail() {
  const { id } = useParams();
  const [thread, setThread] = useState(null);
  const [raw, setRaw] = useState(null);
  const [showRaw, setShowRaw] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    fetchThread(id)
      .then(data => {
        setThread(data);
        setLoading(false);
      })
      .catch(() => {
        setError("Failed to load this context.");
        setLoading(false);
      });
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
      setError("Retry failed. Please try again.");
    }
    setRetrying(false);
  };

  const handleShowRaw = async () => {
    if (!raw) {
      try {
        const data = await fetchRawTranscript(id);
        setRaw(data);
      } catch {
        setError("Failed to load raw transcript.");
        return;
      }
    }
    setShowRaw(!showRaw);
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12 text-center text-gray-500">
        Loading...
      </div>
    );
  }

  if (error && !thread) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12 text-center">
        <p className="text-red-500 mb-4">{error}</p>
        <Link to="/" className="text-gray-500 hover:text-gray-700">
          &larr; Back
        </Link>
      </div>
    );
  }

  const takeaways = thread.key_takeaways || [];
  const artifacts = thread.artifacts || [];
  const openThreads = thread.open_threads || [];
  const tags = thread.tags || [];

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <Link to="/" className="text-sm text-gray-500 hover:text-gray-700 no-underline">
          &larr; Back
        </Link>
        <CopyButton getText={handleCopyContext} />
      </div>

      <h1 className="text-xl font-bold text-gray-900 mb-2">
        {thread.title || "Untitled"}
      </h1>
      <div className="text-sm text-gray-500 mb-1 flex items-center gap-2">
        <span>Pushed {timeAgo(thread.created_at)}</span>
        <span>&middot;</span>
        <span>Source: {thread.source}</span>
        <span>&middot;</span>
        <span>{thread.message_count} messages</span>
        {thread.conversation_type && thread.conversation_type !== "other" && (
          <>
            <span>&middot;</span>
            <span className="px-1.5 py-0.5 text-xs bg-gray-200 text-gray-600 rounded">
              {TYPE_LABELS[thread.conversation_type] || thread.conversation_type}
            </span>
          </>
        )}
      </div>
      {thread.source_url && (
        <a
          href={thread.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-blue-500 hover:text-blue-700"
        >
          Original conversation &rarr;
        </a>
      )}

      {thread.extraction_status === "failed" && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-600 mb-2">
            Extraction failed: {thread.extraction_error}
          </p>
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 cursor-pointer"
          >
            {retrying ? "Retrying..." : "Retry Extraction"}
          </button>
        </div>
      )}

      {thread.summary && (
        <div className="mt-6 p-4 bg-white border border-gray-200 rounded-lg">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Summary</h2>
          <p className="text-sm text-gray-700 leading-relaxed">{thread.summary}</p>
        </div>
      )}

      {takeaways.length > 0 && (
        <div className="mt-4 p-4 bg-white border border-gray-200 rounded-lg">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Key Takeaways</h2>
          <ul className="space-y-1.5">
            {takeaways.map((t, i) => (
              <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                <span className="text-green-500 mt-0.5">{"\u2713"}</span>
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {artifacts.length > 0 && (
        <div className="mt-4 p-4 bg-white border border-gray-200 rounded-lg">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Artifacts</h2>
          <div className="space-y-4">
            {artifacts.map((a, i) => (
              <div key={i}>
                <p className="text-sm text-gray-600 mb-1">
                  {a.description} {a.language && <span className="text-gray-400">({a.language})</span>}
                </p>
                <div className="relative">
                  <pre className="bg-gray-50 border border-gray-200 rounded-md p-3 text-sm text-gray-800 overflow-x-auto">
                    <code>{a.content}</code>
                  </pre>
                  <div className="absolute top-2 right-2">
                    <CopyButton getText={a.content} label="Copy" className="text-xs" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {openThreads.length > 0 && (
        <div className="mt-4 p-4 bg-white border border-gray-200 rounded-lg">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Still Open</h2>
          <ul className="space-y-1.5">
            {openThreads.map((q, i) => (
              <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                <span className="text-gray-400">?</span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {tags.length > 0 && (
        <div className="mt-4 p-4 bg-white border border-gray-200 rounded-lg">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Tags</h2>
          <div className="flex flex-wrap gap-2">
            {tags.map((tag, i) => (
              <span
                key={i}
                className="px-2.5 py-1 text-sm bg-gray-100 text-gray-600 rounded-full"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6">
        <button
          onClick={handleShowRaw}
          className="text-sm text-gray-500 hover:text-gray-700 cursor-pointer"
        >
          {showRaw ? "Hide Raw Transcript \u25B2" : "View Raw Transcript \u25BC"}
        </button>
        {showRaw && raw && (
          <div className="mt-3 p-4 bg-gray-50 border border-gray-200 rounded-lg space-y-4 max-h-96 overflow-y-auto">
            {raw.messages && raw.messages.map((msg, i) => (
              <div key={i}>
                <p className="text-xs font-semibold text-gray-400 uppercase mb-1">
                  {msg.role}
                </p>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{msg.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
