import React from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';

const ALLOWED_MARKDOWN_ELEMENTS = [
  'a',
  'blockquote',
  'br',
  'code',
  'del',
  'em',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'hr',
  'li',
  'mark',
  'ol',
  'p',
  'pre',
  'strong',
  'table',
  'tbody',
  'td',
  'th',
  'thead',
  'tr',
  'ul',
];

export default function MarkdownView({ content = '', className = '' }) {
  return (
    <article className={`markdownView ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        allowedElements={ALLOWED_MARKDOWN_ELEMENTS}
        components={{
          a({ href, children, ...props }) {
            return (
              <a href={href} target="_blank" rel="noreferrer" {...props}>
                {children}
              </a>
            );
          },
          table({ children, ...props }) {
            return (
              <div className="markdownTableWrap">
                <table {...props}>{children}</table>
              </div>
            );
          },
          mark({ children }) {
            return <mark className="markdownMark">{children}</mark>;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </article>
  );
}
