import { useOutletContext } from 'react-router-dom';

export default function EmptyDetail() {
  const ctx = useOutletContext();
  const threads = ctx?.threads || [];
  const hasThreads = threads.length > 0;

  return (
    <div className="h-full flex items-center justify-center p-10">
      <div className="max-w-md text-center">
        <img
          src="/logo.png"
          alt="ContextHub"
          className="w-20 h-20 mx-auto rounded-2xl shadow-lg mb-5 object-contain bg-white"
        />

        <h1 className="text-2xl font-semibold text-ink-900 tracking-tight mb-2">
          {hasThreads ? 'Pick a conversation' : 'Welcome to ContextHub'}
        </h1>
        <p className="text-[15px] text-ink-500 leading-relaxed">
          {hasThreads
            ? 'Select a thread from the sidebar to view its summary, takeaways, artifacts, and full transcript.'
            : 'Push your first conversation from the Chrome extension to see a structured summary, key takeaways, and reusable artifacts here.'}
        </p>
        {!hasThreads && (
          <div className="mt-6 grid grid-cols-3 gap-2 text-left">
            {[
              { n: '1', label: 'Open claude.ai or chatgpt.com' },
              { n: '2', label: 'Click the ContextHub extension' },
              { n: '3', label: 'Push the conversation' },
            ].map(s => (
              <div key={s.n} className="rounded-lg border border-line bg-white p-3">
                <div className="w-6 h-6 rounded-full brand-gradient text-white text-xs font-bold flex items-center justify-center mb-2">
                  {s.n}
                </div>
                <p className="text-[12px] text-ink-700 leading-snug">{s.label}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
