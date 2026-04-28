import { useState } from 'react';

export default function CopyButton({ getText, label = "Copy Context", className = "" }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);

  const handleCopy = async () => {
    try {
      const text = typeof getText === 'function' ? await getText() : getText;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(true);
      setTimeout(() => setError(false), 2000);
    }
  };

  const base = "inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium rounded-lg border transition-all cursor-pointer";
  const state = copied
    ? "bg-emerald-50 border-emerald-300 text-emerald-700"
    : error
    ? "bg-rose-50 border-rose-300 text-rose-700"
    : "brand-gradient text-white border-transparent hover:brightness-110 shadow-sm";

  return (
    <button
      onClick={handleCopy}
      className={`${base} ${state} ${className}`}
    >
      {copied ? (
        <>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
          </svg>
          Copied!
        </>
      ) : error ? (
        "Failed to copy"
      ) : (
        <>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          {label}
        </>
      )}
    </button>
  );
}
