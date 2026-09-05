function cleanInlineMarkdown(value) {
  return value
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .trim();
}

function sentencePoints(value) {
  return cleanInlineMarkdown(value).split(/(?<=[.!?])\s+(?=[A-Z])/).filter(Boolean);
}

function AssistantText({ text }) {
  const blocks = String(text || "").replace(/\r\n/g, "\n").split(/\n\s*\n/).filter(Boolean);

  return <div style={{ display: "grid", gap: 8 }}>{blocks.map((block, blockIndex) => {
    const lines = block.split("\n").map(line => line.trim()).filter(Boolean);
    const listItems = [];
    const content = [];
    let listType = null;
    const flushList = () => {
      if (!listItems.length) return;
      const List = listType === "ordered" ? "ol" : "ul";
      content.push(<List key={`list-${blockIndex}-${content.length}`} style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 4 }}>{listItems.splice(0).map((item, index) => <li key={index}>{item}</li>)}</List>);
      listType = null;
    };

    lines.forEach((line, lineIndex) => {
      const bullet = line.match(/^[-*•]\s+(.+)$/);
      const ordered = line.match(/^\d+[.)]\s+(.+)$/);
      const heading = line.match(/^(?:#{1,6}\s+(.+)|\*\*(.+)\*\*)$/);
      if (bullet || ordered) {
        const nextType = ordered ? "ordered" : "unordered";
        if (listType && listType !== nextType) flushList();
        listType = nextType;
        listItems.push(cleanInlineMarkdown((bullet || ordered)[1]));
        return;
      }

      flushList();
      if (heading) {
        content.push(<strong key={`heading-${blockIndex}-${lineIndex}`}>{cleanInlineMarkdown(heading[1] || heading[2])}</strong>);
        return;
      }
      const points = sentencePoints(line);
      content.push(points.length > 1
        ? <ul key={`points-${blockIndex}-${lineIndex}`} style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 4 }}>{points.map((point, index) => <li key={index}>{point}</li>)}</ul>
        : <div key={`text-${blockIndex}-${lineIndex}`}>{points[0]}</div>);
    });
    flushList();
    return <div key={blockIndex} style={{ display: "grid", gap: 5 }}>{content}</div>;
  })}</div>;
}

export default function ChatMessage({ role, text, analysis }) {
  return <div className={`chat-row ${role === "user" ? "user" : "assistant"}`}><div className="bubble">{role === "assistant" ? <AssistantText text={text} /> : text}{analysis && <div className="small-muted" style={{ marginTop: 8 }}>
    {analysis.emotion?.label && <>Emotion: {analysis.emotion.label} · </>}
    {analysis.risk?.tier && <>Risk: {analysis.risk.tier}</>}
    {analysis.voice && <> · Voice: {analysis.voice.vocal_tone || "analyzed"}</>}
    {analysis.rag?.is_used && <> · Support guidance used{analysis.rag.sources?.length ? `: ${analysis.rag.sources.join(", ")}` : ""}</>}
  </div>}</div></div>;
}
