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

  return (
    <button
      onClick={handleCopy}
      className={`px-3 py-1.5 text-sm rounded-md border transition-colors cursor-pointer ${
        copied
          ? "bg-green-50 border-green-300 text-green-700"
          : error
          ? "bg-red-50 border-red-300 text-red-700"
          : "bg-white border-gray-300 text-gray-700 hover:bg-gray-50"
      } ${className}`}
    >
      {copied ? "Copied!" : error ? "Failed to copy" : label}
    </button>
  );
}
