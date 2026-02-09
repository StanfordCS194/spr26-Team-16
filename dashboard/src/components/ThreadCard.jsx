import { Link } from 'react-router-dom';
import { timeAgo } from '../utils/timeAgo';
import { formatContext } from '../utils/formatContext';
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

export default function ThreadCard({ thread }) {
  if (thread.extraction_status === "failed") {
    return (
      <div className="bg-white border border-red-200 rounded-lg shadow-sm p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-red-600">Extraction Failed</p>
            <p className="text-xs text-gray-500 mt-1">{timeAgo(thread.created_at)}</p>
            {thread.extraction_error && (
              <p className="text-xs text-red-400 mt-1">{thread.extraction_error}</p>
            )}
          </div>
          <Link
            to={`/thread/${thread.id}`}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            View &rarr;
          </Link>
        </div>
      </div>
    );
  }

  if (thread.extraction_status === "pending" || thread.extraction_status === "processing") {
    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
          <p className="text-sm text-gray-500">Extracting context...</p>
        </div>
      </div>
    );
  }

  const takeaways = thread.key_takeaways || [];
  const openThreads = thread.open_threads || [];
  const tags = thread.tags || [];

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div>
          <Link
            to={`/thread/${thread.id}`}
            className="text-base font-semibold text-gray-900 hover:text-gray-600 no-underline"
          >
            {thread.title}
          </Link>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs text-gray-400">{timeAgo(thread.created_at)}</span>
            {thread.conversation_type && thread.conversation_type !== "other" && (
              <span className="px-1.5 py-0.5 text-xs bg-gray-200 text-gray-600 rounded">
                {TYPE_LABELS[thread.conversation_type] || thread.conversation_type}
              </span>
            )}
          </div>
        </div>
      </div>

      {thread.summary && (
        <p className="text-sm text-gray-600 leading-relaxed">{thread.summary}</p>
      )}

      {takeaways.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-500 mb-1">Key takeaways:</p>
          <ul className="text-sm text-gray-700 space-y-0.5">
            {takeaways.slice(0, 3).map((t, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span className="text-gray-400 mt-0.5">&bull;</span>
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {openThreads.length > 0 && (
        <p className="text-sm text-gray-500 italic">
          Open: {openThreads[0]}
        </p>
      )}

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag, i) => (
            <span
              key={i}
              className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between pt-1 border-t border-gray-100">
        <CopyButton getText={() => formatContext(thread)} />
        <Link
          to={`/thread/${thread.id}`}
          className="text-sm text-gray-500 hover:text-gray-700 no-underline"
        >
          View &rarr;
        </Link>
      </div>
    </div>
  );
}
