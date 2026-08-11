import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, useLocation, useNavigate } from 'react-router-dom';
import { Button, ConfigProvider, Flex, Layout, Space, Typography, theme } from 'antd';
import { ExportOutlined, LoginOutlined, MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons';
import AppSidebar from './components/AppSidebar.jsx';
import ChatComposer from './components/ChatComposer.jsx';
import EmptyChatCanvas from './components/EmptyChatCanvas.jsx';
import InsightSidebar from './components/InsightSidebar.jsx';
import LoadingAssistantMessage from './components/LoadingAssistantMessage.jsx';
import MessageBubble from './components/MessageBubble.jsx';
import TopicDetailPage from './pages/TopicDetailPage.jsx';
import TopicListPage from './pages/TopicListPage.jsx';
import { readApiResponse } from './utils/api.js';
import { getOrCreateUserId, mergeAgentStep } from './utils/chat.js';
import './styles.css';

const { Header, Content } = Layout;
const { Text } = Typography;

function TopicPulseApp() {
  const [collapsed, setCollapsed] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [panelMode, setPanelMode] = useState('insight');
  const [tools, setTools] = useState({ web: true, memory: true });
  const [lastSteps, setLastSteps] = useState([]);
  const [chatSessions, setChatSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState('');
  const [topics, setTopics] = useState([]);
  const [selectedTopic, setSelectedTopic] = useState(null);
  const [topicsLoading, setTopicsLoading] = useState(false);
  const [topicDetailLoading, setTopicDetailLoading] = useState(false);
  const [topicsError, setTopicsError] = useState('');
  const [userId] = useState(getOrCreateUserId);
  const inputRef = useRef(null);
  const conversationPaneRef = useRef(null);
  const sessionLoadTokenRef = useRef(0);
  const creatingNewChatRef = useRef(false);
  const location = useLocation();
  const navigate = useNavigate();
  const activeView = location.pathname.startsWith('/topics') ? 'topics' : 'chat';
  const routedSessionId = activeView === 'chat' && location.pathname.startsWith('/chat/')
    ? decodeURIComponent(location.pathname.slice('/chat/'.length))
    : '';
  const routedTopicId = activeView === 'topics' && location.pathname.startsWith('/topics/')
    ? decodeURIComponent(location.pathname.slice('/topics/'.length))
    : '';

  const latestTopic = useMemo(() => {
    const latest = [...messages].reverse().find((item) => item.role === 'user');
    return latest?.content || '等待新的分析任务';
  }, [messages]);

  function createNewChat() {
    sessionLoadTokenRef.current += 1;
    creatingNewChatRef.current = true;
    navigate('/chat');
    setMessages([]);
    setInput('');
    setSessionId(null);
    setLastSteps([]);
    inputRef.current?.focus?.();
  }

  async function loadChatSessions() {
    setSessionsLoading(true);
    setSessionsError('');
    try {
      const response = await fetch('/api/sessions');
      const data = await readApiResponse(response, '最近会话加载失败');
      setChatSessions(data.sessions || []);
    } catch (error) {
      setSessionsError(error.message || '最近会话加载失败');
    } finally {
      setSessionsLoading(false);
    }
  }

  async function loadSessionDetail(nextSessionId) {
    if (!nextSessionId || loading) return;
    const loadToken = sessionLoadTokenRef.current + 1;
    sessionLoadTokenRef.current = loadToken;
    setSessionsError('');
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(nextSessionId)}`);
      const data = await readApiResponse(response, '会话加载失败');
      if (loadToken !== sessionLoadTokenRef.current) {
        return;
      }
      setSessionId(data.id);
      setLastSteps([]);
      setInput('');
      setMessages(
        (data.messages || [])
          .filter((message) => message.role === 'user' || message.role === 'assistant')
          .map((message) => ({
            role: message.role,
            content: message.content,
            completed: message.completed,
            query_key: message.query_key,
            reference_data: message.reference_data || [],
            topic_update: message.topic_update || {},
            at: message.created_at,
          })),
      );
    } catch (error) {
      if (loadToken !== sessionLoadTokenRef.current) {
        return;
      }
      if (error.status === 404 || error.message === 'Session not found') {
        setSessionId(null);
        setMessages([]);
        setLastSteps([]);
        setInput('');
        navigate('/chat', { replace: true });
        return;
      }
      setSessionsError(error.message || '会话加载失败');
    }
  }

  async function loadTopics() {
    setTopicsLoading(true);
    setTopicsError('');
    try {
      const response = await fetch('/api/topics');
      const data = await readApiResponse(response, '话题列表加载失败');
      setTopics(data.topics || []);
    } catch (error) {
      setTopicsError(error.message || '话题列表加载失败');
    } finally {
      setTopicsLoading(false);
    }
  }

  async function loadTopicDetail(topicId) {
    if (!topicId) return;
    setTopicDetailLoading(true);
    setTopicsError('');
    try {
      const response = await fetch(`/api/topics/${encodeURIComponent(topicId)}`);
      const data = await readApiResponse(response, '话题详情加载失败');
      setSelectedTopic(data);
    } catch (error) {
      setTopicsError(error.message || '话题详情加载失败');
    } finally {
      setTopicDetailLoading(false);
    }
  }

  function selectTopic(topic) {
    navigate(`/topics/${encodeURIComponent(topic.id)}`);
  }

  useEffect(() => {
    if (location.pathname === '/') {
      navigate('/chat', { replace: true });
      return;
    }
    if (!location.pathname.startsWith('/chat') && !location.pathname.startsWith('/topics')) {
      navigate('/chat', { replace: true });
    }
  }, [location.pathname, navigate]);

  useEffect(() => {
    loadChatSessions();
  }, []);

  useEffect(() => {
    if (location.pathname === '/chat') {
      creatingNewChatRef.current = false;
    }
  }, [location.pathname]);

  useEffect(() => {
    if (creatingNewChatRef.current) {
      return;
    }
    if (activeView !== 'chat' || !routedSessionId || routedSessionId === sessionId) {
      return;
    }
    loadSessionDetail(routedSessionId);
  }, [activeView, routedSessionId, sessionId]);

  useEffect(() => {
    if (activeView === 'topics') {
      loadTopics();
    }
  }, [activeView]);

  useEffect(() => {
    if (activeView !== 'topics') {
      setSelectedTopic(null);
      return;
    }
    if (routedTopicId) {
      loadTopicDetail(routedTopicId);
    } else {
      setSelectedTopic(null);
    }
  }, [activeView, routedTopicId]);

  useEffect(() => {
    if (activeView !== 'chat' || !routedSessionId || messages.length === 0 || loading) {
      return;
    }
    scrollConversationToBottom('auto', 2);
  }, [activeView, routedSessionId, messages.length, loading]);

  async function copyMessage(content) {
    await window.navigator.clipboard?.writeText(content);
  }

  function scrollConversationToBottom(behavior = 'smooth', frames = 1) {
    window.requestAnimationFrame(() => {
      const pane = conversationPaneRef.current;
      if (!pane) return;
      pane.scrollTo({ top: pane.scrollHeight, behavior });
      if (frames > 1) {
        scrollConversationToBottom(behavior, frames - 1);
      }
    });
  }

  async function sendMessage(text) {
    const message = text.trim();
    if (!message || loading) return;

    const assistantId = window.crypto?.randomUUID?.() || `assistant-${Date.now()}`;
    const nextMessages = [
      ...messages,
      { role: 'user', content: message, at: new Date().toISOString() },
      {
        id: assistantId,
        role: 'assistant',
        content: '',
        completed: false,
        status: '正在连接',
        query_key: null,
        reference_data: [],
        topic_update: {},
        steps: [],
        at: new Date().toISOString(),
      },
    ];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);
    scrollConversationToBottom();

    const updateAssistantMessage = (updater) => {
      setMessages((current) =>
        current.map((item) => {
          if (item.id !== assistantId) return item;
          return { ...item, ...updater(item) };
        }),
      );
    };

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          user_id: userId,
          session_id: sessionId,
        }),
      });

      if (!response.ok || !response.body) {
        const errorPayload = await readApiResponse(response, '请求失败');
        throw new Error(errorPayload?.message || '请求失败');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);

          if (event.type === 'status') {
            updateAssistantMessage(() => ({ status: event.text || '' }));
            scrollConversationToBottom();
          }

          if (event.type === 'references') {
            updateAssistantMessage(() => ({
              query_key: event.query_key,
              reference_data: event.reference_data || [],
            }));
            scrollConversationToBottom();
          }

          if (event.type === 'topic_update') {
            updateAssistantMessage(() => ({
              topic_update: event.topic_update || {},
            }));
            scrollConversationToBottom();
          }

          if (event.type === 'agent_step') {
            updateAssistantMessage((item) => ({
              steps: mergeAgentStep(item.steps || [], event),
            }));
            scrollConversationToBottom();
          }

          if (event.type === 'delta') {
            updateAssistantMessage((item) => ({
              content: `${item.content || ''}${event.content || ''}`,
              status: '',
            }));
            scrollConversationToBottom();
          }

          if (event.type === 'done') {
            setSessionId(event.session_id);
            if (event.session_id) {
              navigate(`/chat/${encodeURIComponent(event.session_id)}`, { replace: true });
            }
            setLastSteps(event.steps || []);
            updateAssistantMessage((item) => ({
              completed: event.completed,
              query_key: event.query_key,
              reference_data: event.reference_data || [],
              topic_update: event.topic_update || {},
              steps: item.steps?.length ? item.steps : event.steps || [],
              status: '',
            }));
            scrollConversationToBottom();
          }

          if (event.type === 'error') {
            throw new Error(event.message || '请求失败');
          }
        }
      }
      loadChatSessions();
    } catch (error) {
      updateAssistantMessage(() => ({
        content: `请求失败：${error.message || '请确认后端服务已启动，并检查网络连接。'}`,
        completed: false,
        error: true,
        status: '',
      }));
    } finally {
      setLoading(false);
    }
  }

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: '#4f46e5',
          colorInfo: '#0891b2',
          colorSuccess: '#10b981',
          colorWarning: '#f59e0b',
          borderRadius: 8,
          fontFamily:
            'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif',
        },
        components: {
          Layout: {
            bodyBg: '#f7f8fc',
            headerBg: 'rgba(255,255,255,.88)',
            siderBg: '#ffffff',
          },
          Card: {
            borderRadiusLG: 8,
          },
          Button: {
            borderRadius: 8,
            controlHeight: 36,
          },
        },
      }}
    >
      <Layout className="appShell">
        <AppSidebar
          activeView={activeView}
          chatSessions={chatSessions}
          collapsed={collapsed}
          currentSessionId={sessionId}
          onCreateNewChat={createNewChat}
          onNavigate={navigate}
          routedSessionId={routedSessionId}
          sessionsError={sessionsError}
          sessionsLoading={sessionsLoading}
          userId={userId}
        />

        <Layout className="workspace">
          <Header className="topbar">
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((value) => !value)}
              aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
            />
            <Flex vertical align="center" className="topTitle">
              <Text strong>{activeView === 'topics' ? '已关注话题' : '新对话'}</Text>
              <Text type="secondary">
                {activeView === 'topics'
                  ? selectedTopic?.title || '浏览 data/topics 中的 Markdown 话题'
                  : sessionId
                    ? `会话 ${sessionId.slice(0, 12)}`
                    : '准备接收新的热点分析任务'}
              </Text>
            </Flex>
            <Space>
              <Button icon={<ExportOutlined />}>导出</Button>
              <Button type="primary" icon={<LoginOutlined />}>
                登录
              </Button>
            </Space>
          </Header>

          <Layout className={`mainLayout ${activeView === 'topics' ? 'isTopicMode' : ''}`}>
            <Content ref={conversationPaneRef} className="conversationPane">
              {activeView === 'topics' ? (
                routedTopicId ? (
                  <TopicDetailPage
                    topic={selectedTopic}
                    loading={topicDetailLoading}
                    onBack={() => navigate('/topics')}
                  />
                ) : (
                  <TopicListPage
                    topics={topics}
                    loading={topicsLoading}
                    error={topicsError}
                    onReload={loadTopics}
                    onSelectTopic={selectTopic}
                  />
                )
              ) : messages.length === 0 ? (
                <EmptyChatCanvas onPrompt={sendMessage} />
              ) : (
                <div className="messageList">
                  {messages.map((message, index) => (
                    <MessageBubble key={`${message.role}-${index}`} message={message} onCopy={copyMessage} />
                  ))}
                  {loading && !messages.some((message) => message.role === 'assistant' && message.completed === false) && (
                    <LoadingAssistantMessage />
                  )}
                </div>
              )}
            </Content>

            {activeView === 'chat' && (
              <InsightSidebar
                lastSteps={lastSteps}
                latestTopic={latestTopic}
                messages={messages}
                panelMode={panelMode}
                setPanelMode={setPanelMode}
                tools={tools}
              />
            )}
          </Layout>

          {activeView === 'chat' && (
            <ChatComposer
              input={input}
              inputRef={inputRef}
              loading={loading}
              onInputChange={setInput}
              onSend={sendMessage}
              setTools={setTools}
              tools={tools}
            />
          )}
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <TopicPulseApp />
  </BrowserRouter>,
);
