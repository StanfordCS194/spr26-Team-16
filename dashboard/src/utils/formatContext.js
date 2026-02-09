export function formatContext(thread) {
  let output = `[Context from ContextHub]\n`;
  output += `Continuing from a previous conversation: ${thread.title}\n\n`;
  output += `${thread.summary}\n`;

  if (thread.key_takeaways && thread.key_takeaways.length > 0) {
    output += `\nKey takeaways:\n`;
    thread.key_takeaways.forEach(t => { output += `- ${t}\n`; });
  }

  if (thread.open_threads && thread.open_threads.length > 0) {
    output += `\nStill open:\n`;
    thread.open_threads.forEach(t => { output += `- ${t}\n`; });
  }

  if (thread.artifacts && thread.artifacts.length > 0) {
    if (thread.artifacts.length <= 3) {
      output += `\nArtifacts from that conversation:\n`;
      thread.artifacts.forEach(a => {
        output += `[${a.description}]\n`;
        output += `\`\`\`${a.language || ''}\n${a.content}\n\`\`\`\n`;
      });
    } else {
      output += `\nNote: ${thread.artifacts.length} artifacts were produced. Ask me to share specific ones if needed.\n`;
    }
  }

  output += `[End Context]`;
  return output;
}
