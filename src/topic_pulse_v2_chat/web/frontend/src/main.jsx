import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const suggestions = [
  '关注最近互联网大厂因 AI 裁员的信息',
  '查询某个新闻话题的最新进展',
  '整理一个热点事件的时间线',
  '把这次查询结果保存到本地记忆',
  '查看已关注话题的最新状态',
  '分析一条新闻的关键争议点',
];

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(false);

  async function sendMessage(text) {
    const message = text.trim();
    if (!message || loading) return;
    const nextMessages = [...messages, { role: 'user', content: message }];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          history: messages,
        }),
      });
      const data = await response.json();
      setSessionId(data.session_id);
      setMessages([...nextMessages, { role: 'assistant', content: data.answer }]);
    } catch (error) {
      setMessages([
        ...nextMessages,
        { role: 'assistant', content: '请求失败，请确认后端服务已启动。' },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    sendMessage(input);
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="avatar">T</div>
          <span>Topic Pulse</span>
        </div>
        <button className="navItem active">新对话</button>
        <button className="navItem">话题记忆</button>
        <button className="navItem">搜索记录</button>
        <div className="sidebarFooter">关于 Topic Pulse</div>
      </aside>

      <main className="chat">
        <header className="topbar">
          <button className="iconButton" aria-label="折叠侧边栏">☰</button>
          <div className="title">
            <strong>新对话</strong>
            <span>AI 生成内容请谨慎核实</span>
          </div>
          <button className="loginButton">登录</button>
        </header>

        <section className="content">
          {messages.length === 0 ? (
            <div className="empty">
              <h1>有什么我能帮你的吗？</h1>
              <div className="suggestions">
                {suggestions.map((item) => (
                  <button key={item} onClick={() => sendMessage(item)}>
                    {item}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="messages">
              {messages.map((message, index) => (
                <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                  <div className="bubble">{message.content}</div>
                </article>
              ))}
              {loading && (
                <article className="message assistant">
                  <div className="bubble muted">正在思考...</div>
                </article>
              )}
            </div>
          )}
        </section>

        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                handleSubmit(event);
              }
            }}
            placeholder="发消息..."
            rows="2"
          />
          <div className="composerActions">
            <button type="button" className="toolButton">＋</button>
            <button type="button" className="toolButton">联网</button>
            <button type="button" className="toolButton">记忆</button>
            <button type="submit" className="sendButton" disabled={loading || !input.trim()}>
              发送
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
