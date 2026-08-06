import React from 'react';

function renderInline(text) {
  const nodes = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|https?:\/\/\S+)/g;
  let cursor = 0;
  let match;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      nodes.push(text.slice(cursor, match.index));
    }

    const token = match[0];
    const key = `${match.index}-${token.slice(0, 12)}`;

    if (token.startsWith('`') && token.endsWith('`')) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>);
    } else if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith('[')) {
      const linkMatch = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
      if (linkMatch) {
        nodes.push(
          <a href={linkMatch[2]} target="_blank" rel="noreferrer" key={key}>
            {linkMatch[1]}
          </a>,
        );
      } else {
        nodes.push(token);
      }
    } else {
      nodes.push(
        <a href={token} target="_blank" rel="noreferrer" key={key}>
          {token}
        </a>,
      );
    }

    cursor = match.index + token.length;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }

  return nodes;
}

export default function MarkdownView({ content = '', className = '' }) {
  const lines = content.split(/\r?\n/);
  const blocks = [];
  let codeLines = [];
  let inCode = false;

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    const key = `${index}-${trimmed.slice(0, 16)}`;

    if (trimmed.startsWith('```')) {
      if (inCode) {
        blocks.push(
          <pre key={`code-${index}`}>
            <code>{codeLines.join('\n')}</code>
          </pre>,
        );
        codeLines = [];
      }
      inCode = !inCode;
      return;
    }

    if (inCode) {
      codeLines.push(line);
      return;
    }

    if (!trimmed) {
      blocks.push(<div className="markdownGap" key={key} />);
      return;
    }

    if (trimmed.startsWith('### ')) {
      blocks.push(<h3 key={key}>{renderInline(trimmed.slice(4))}</h3>);
      return;
    }

    if (trimmed.startsWith('## ')) {
      blocks.push(<h2 key={key}>{renderInline(trimmed.slice(3))}</h2>);
      return;
    }

    if (trimmed.startsWith('# ')) {
      blocks.push(<h1 key={key}>{renderInline(trimmed.slice(2))}</h1>);
      return;
    }

    if (trimmed.startsWith('> ')) {
      blocks.push(<blockquote key={key}>{renderInline(trimmed.slice(2))}</blockquote>);
      return;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      blocks.push(
        <div className="markdownBullet" key={key}>
          <span />
          <p>{renderInline(unordered[1])}</p>
        </div>,
      );
      return;
    }

    const ordered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      blocks.push(
        <div className="markdownBullet markdownOrdered" key={key}>
          <span>{trimmed.match(/^\d+/)?.[0]}</span>
          <p>{renderInline(ordered[1])}</p>
        </div>,
      );
      return;
    }

    blocks.push(<p key={key}>{renderInline(trimmed)}</p>);
  });

  if (inCode && codeLines.length > 0) {
    blocks.push(
      <pre key="code-tail">
        <code>{codeLines.join('\n')}</code>
      </pre>,
    );
  }

  return <article className={`markdownView ${className}`.trim()}>{blocks}</article>;
}
