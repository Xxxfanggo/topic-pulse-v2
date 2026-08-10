import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, useLocation, useNavigate } from 'react-router-dom';
import {
  Avatar,
  Badge,
  Button,
  Card,
  ConfigProvider,
  Divider,
  Flex,
  Input,
  Layout,
  Menu,
  Progress,
  Segmented,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
  theme,
} from 'antd';
import {
  BulbOutlined,
  ClockCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  ExportOutlined,
  GlobalOutlined,
  LoginOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  PlusOutlined,
  RightOutlined,
  SendOutlined,
  StarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import TopicDetailPage from './pages/TopicDetailPage.jsx';
import TopicListPage from './pages/TopicListPage.jsx';
import MarkdownView from './components/MarkdownView.jsx';
import { readApiResponse } from './utils/api.js';
import './styles.css';

const { Header, Sider, Content } = Layout;
const { Text, Title, Paragraph } = Typography;

const STORAGE_KEY = 'topic_pulse_user_id';

const starterPrompts = [
  {
    label: '时间线',
    title: '追踪热点事件',
    prompt: '追踪最近 24 小时 AI 搜索产品的舆论变化，按时间线总结关键节点。',
  },
  {
    label: '争议分析',
    title: '提炼争议焦点',
    prompt: '分析这条新闻下的核心争议点、主要立场和还需要核验的信息。',
  },
  {
    label: '记忆',
    title: '持续关注话题',
    prompt: '把“AI Agent 商业化”加入关注，并告诉我今天有什么新进展。',
  },
  {
    label: '简报',
    title: '生成团队简报',
    prompt: '为我生成一份面向团队晨会的热点简报，包含摘要、风险和行动建议。',
  },
];

const memories = [
  { label: 'AI Agent 商业化', status: '活跃', score: 92 },
  { label: '大模型价格战', status: '升温', score: 87 },
  { label: '跨境电商监管', status: '观察', score: 73 },
];

const signalMetrics = [
  { label: '舆情热度', value: 82, color: '#f59e0b' },
  { label: '信源可信度', value: 76, color: '#0891b2' },
  { label: '争议强度', value: 58, color: '#6366f1' },
];

function getOrCreateUserId() {
  const existing = window.localStorage.getItem(STORAGE_KEY);
  if (existing) return existing;
  const generated =
    window.crypto?.randomUUID?.() || `anonymous-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  window.localStorage.setItem(STORAGE_KEY, generated);
  return generated;
}

function formatSessionTime(value) {
  if (!value) return '刚刚';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '刚刚';
  const diffMs = Date.now() - date.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diffMs < minute) return '刚刚';
  if (diffMs < hour) return `${Math.max(1, Math.floor(diffMs / minute))} 分钟前`;
  if (diffMs < day) return `${Math.floor(diffMs / hour)} 小时前`;
  if (diffMs < 2 * day) return '昨天';
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

function normalizeReferenceData(referenceData) {
  if (!Array.isArray(referenceData)) return [];
  const seen = new Set();
  return referenceData
    .map((item) => {
      const title = item?.title || '';
      const link = item?.url || item?.link || '';
      return {
        title: String(title).trim(),
        link: String(link).trim(),
      };
    })
    .filter((item) => {
      if (!item.title || !item.link || seen.has(item.link)) return false;
      seen.add(item.link);
      return true;
    });
}

function ReferencePanel({ queryKey, referenceData }) {
  const [expanded, setExpanded] = useState(false);
  const references = normalizeReferenceData(referenceData);
  const keywordText = String(queryKey || '').trim();
  if (!keywordText && references.length === 0) return null;

  return (
    <div className={`referencePanel ${expanded ? 'isExpanded' : ''}`}>
      <button type="button" className="referenceToggle" onClick={() => setExpanded((value) => !value)}>
        <GlobalOutlined />
        <span>搜索 {keywordText ? 1 : 0} 个关键词，参考 {references.length} 篇资料</span>
        <RightOutlined className="referenceChevron" />
      </button>
      {expanded && (
        <div className="referenceBody">
          {keywordText && <Text className="referenceQuery">“{keywordText}”</Text>}
          {references.length > 0 && (
            <ol className="referenceList">
              {references.slice(0, 18).map((reference, index) => (
                <li key={`${reference.link}-${index}`}>
                  <a href={reference.link} target="_blank" rel="noreferrer">
                    {reference.title}
                  </a>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

function normalizeTopicItems(items) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => ({
      date: String(item?.date || '').trim(),
      title: String(item?.title || '').trim(),
      source: String(item?.source || '').trim(),
      url: String(item?.url || '').trim(),
      summary: String(item?.summary || '').trim(),
    }))
    .filter((item) => item.title);
}

function TopicUpdatePanel({ update }) {
  const [expanded, setExpanded] = useState(false);
  if (!update || !update.topic_name) return null;

  const newItems = normalizeTopicItems(update.new_items);
  const existingItems = normalizeTopicItems(update.existing_items);
  const newCount = Number(update.new_count || newItems.length || 0);
  const existingCount = Number(update.existing_count || existingItems.length || 0);
  const hasNew = newCount > 0;
  const statusText = hasNew
    ? `本次发现 ${newCount} 条新信息`
    : '本次未发现新增信息';

  return (
    <div className={`topicUpdatePanel ${expanded ? 'isExpanded' : ''} ${hasNew ? 'hasNew' : 'noNew'}`}>
      <button type="button" className="topicUpdateToggle" onClick={() => setExpanded((value) => !value)}>
        <StarOutlined />
        <span>{update.topic_name}：{statusText}</span>
        {existingCount > 0 && <Tag color="default">已有 {existingCount}</Tag>}
        <RightOutlined className="referenceChevron" />
      </button>
      {expanded && (
        <div className="topicUpdateBody">
          {newItems.length > 0 && (
            <div className="topicUpdateGroup">
              <Text strong>新增信息</Text>
              <div className="topicUpdateList">
                {newItems.slice(0, 6).map((item, index) => (
                  <div className="topicUpdateItem isNew" key={`${item.url || item.title}-${index}`}>
                    <Tag color="success">新增</Tag>
                    <div className="topicUpdateCopy">
                      <Text strong>{item.title}</Text>
                      <Text type="secondary">
                        {[item.date, item.source].filter(Boolean).join(' · ')}
                      </Text>
                      {item.summary && <Text className="topicUpdateSummary">{item.summary}</Text>}
                      {item.url && <a href={item.url} target="_blank" rel="noreferrer">查看来源</a>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {existingItems.length > 0 && (
            <div className="topicUpdateGroup">
              <Text strong>已记录信息</Text>
              <div className="topicUpdateList compact">
                {existingItems.map((item, index) => (
                  <div className="topicUpdateItem" key={`${item.url || item.title}-${index}`}>
                    <Tag>已记录</Tag>
                    <div className="topicUpdateCopy">
                      <Text>{item.title}</Text>
                      <Text type="secondary">
                        {[item.date, item.source].filter(Boolean).join(' · ')}
                      </Text>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PulseGraph() {
  return (
    <div className="pulseGraph" aria-hidden="true">
      <span className="node nodeA" />
      <span className="node nodeB" />
      <span className="node nodeC" />
      <span className="line lineOne" />
      <span className="line lineTwo" />
      <span className="line lineThree" />
    </div>
  );
}

function mergeAgentStep(steps = [], step = {}) {
  const key = `${step.step_index || steps.length + 1}-${step.title || step.tool_name || ''}`;
  const nextStep = { ...step, key };
  const index = steps.findIndex((item) => item.key === key);
  if (index === -1) {
    return [...steps, nextStep];
  }
  return steps.map((item, itemIndex) => (itemIndex === index ? { ...item, ...nextStep } : item));
}

function MessageBubble({ message, onCopy }) {
  const isUser = message.role === 'user';

  return (
    <Flex className={`chatMessage ${isUser ? 'isUser' : 'isAssistant'} ${message.error ? 'isError' : ''}`} gap={12}>
      <Avatar className="messageAvatar">{isUser ? '你' : 'TP'}</Avatar>
      <div className="messageMain">
        <Flex align="center" gap={8} className="messageMeta">
          <Text strong>{isUser ? '你' : 'Topic Pulse'}</Text>
          {!isUser && message.completed === false && <Tag color="warning">未完成</Tag>}
        </Flex>
        <Card size="small" className="bubbleCard">
          {!isUser && !message.error && (
            <>
              <TopicUpdatePanel update={message.topic_update} />
              <ReferencePanel queryKey={message.query_key} referenceData={message.reference_data} />
            </>
          )}
          {!isUser && message.status && !message.content && (
            <Text type="secondary" className="messageStatus">
              <span className="statusSpinner" aria-hidden="true" />
              {message.status}
            </Text>
          )}
          {isUser || message.error ? (
            <Paragraph className="messageText">{message.content}</Paragraph>
          ) : (
            <MarkdownView content={message.content} className="messageMarkdown" />
          )}
          {!isUser && message.steps?.length > 0 && (
            <>
              <Divider className="compactDivider" />
              <div className="stepList">
                {message.steps.slice(0, 5).map((step, index) => (
                  <div className={`stepItem ${step.status ? `is-${step.status}` : ''}`} key={step.key || `${index}-${step.action || step.tool_name || 'step'}`}>
                    <span className="stepDot" />
                    <div className="stepCopy">
                      <Text strong>{step.title || `Step ${index + 1}`}</Text>
                      <Text type="secondary">
                        {step.detail || step.thought || step.action || step.tool_name || step.final_answer || '正在整理推理步骤'}
                      </Text>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
        <Tooltip title="复制消息">
          <Button size="small" type="text" icon={<CopyOutlined />} onClick={() => onCopy(message.content)} />
        </Tooltip>
      </div>
    </Flex>
  );
}

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

  const menuItems = [
    { key: 'chat', icon: <MessageOutlined />, label: '当前对话' },
    { key: 'topics', icon: <StarOutlined />, label: '已关注话题' },
  ];

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
        <Sider className="appSider" width={280} collapsedWidth={0} collapsed={collapsed} trigger={null}>
          <Flex vertical gap={16} className="siderInner">
            <Flex align="center" gap={12} className="brand">
              <Avatar shape="square" className="brandAvatar">
                TP
              </Avatar>
              <div className="brandCopy">
                <Text strong>Topic Pulse</Text>
                <Text type="secondary">告别信息焦虑~</Text>
              </div>
            </Flex>

            <Button type="primary" block icon={<PlusOutlined />} onClick={createNewChat}>
              新建对话
            </Button>

            <Menu
              mode="inline"
              selectedKeys={[activeView === 'topics' ? 'topics' : 'chat']}
              items={menuItems}
              className="navMenu"
              onClick={({ key }) => {
                if (key === 'topics') {
                  navigate('/topics');
                } else {
                  navigate('/chat');
                }
              }}
            />

            <div className="siderSection">
              <Text type="secondary" className="sectionTitle">
                最近会话
              </Text>
              <div className="sessionList">
                {sessionsLoading && chatSessions.length === 0 && (
                  <Text type="secondary" className="sessionHint">正在加载会话...</Text>
                )}
                {sessionsError && (
                  <Text type="danger" className="sessionHint">{sessionsError}</Text>
                )}
                {!sessionsLoading && chatSessions.length === 0 && !sessionsError && (
                  <Text type="secondary" className="sessionHint">暂无历史会话</Text>
                )}
                {chatSessions.map((item, index) => (
                  <button
                    type="button"
                    className={item.id === (routedSessionId || sessionId) ? 'sessionItem active' : 'sessionItem'}
                    key={item.id}
                    onClick={() => navigate(`/chat/${encodeURIComponent(item.id)}`)}
                  >
                    <Avatar size="small" icon={index === 0 ? <ThunderboltOutlined /> : <ClockCircleOutlined />} />
                    <div className="sessionCopy">
                      <Text ellipsis strong={item.id === (routedSessionId || sessionId)}>
                        {item.title}
                      </Text>
                      <Text type="secondary">{formatSessionTime(item.updated_at)}</Text>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <Card size="small" className="visitorCard">
              <Flex align="center" gap={10}>
                <Avatar>访</Avatar>
                <div>
                  <Text strong>访客模式</Text>
                  <Text type="secondary" className="blockText">
                    {userId.slice(0, 8)}
                  </Text>
                </div>
              </Flex>
            </Card>
          </Flex>
        </Sider>

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
                <div className="emptyCanvas">
                  <PulseGraph />
                  <Flex vertical align="center" gap={6} className="heroCopy">
                    <Text className="heroEyebrow">Topic Pulse</Text>
                    <Title level={1}>把热点线索整理成可行动的判断。</Title>
                    <Paragraph>
                      输入新闻、话题或追踪目标，系统会结合记忆、检索和 ReAct 推理返回分析结果。
                    </Paragraph>
                  </Flex>
                  <div className="promptGrid">
                    {starterPrompts.map((item) => (
                      <Card
                        key={item.title}
                        hoverable
                        className="promptCard"
                        onClick={() => sendMessage(item.prompt)}
                      >
                        <Tag color="geekblue">{item.label}</Tag>
                        <Title level={5}>{item.title}</Title>
                        <Paragraph ellipsis={{ rows: 2 }}>{item.prompt}</Paragraph>
                      </Card>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="messageList">
                  {messages.map((message, index) => (
                    <MessageBubble key={`${message.role}-${index}`} message={message} onCopy={copyMessage} />
                  ))}
                  {loading && !messages.some((message) => message.role === 'assistant' && message.completed === false) && (
                    <Flex className="chatMessage isAssistant" gap={12}>
                      <Avatar className="messageAvatar">TP</Avatar>
                      <div className="messageMain">
                        <Flex align="center" gap={8} className="messageMeta">
                          <Text strong>Topic Pulse</Text>
                          <Badge status="processing" text="推理中" />
                        </Flex>
                        <Card size="small" className="bubbleCard loadingCard">
                          <span />
                          <span />
                          <span />
                        </Card>
                      </div>
                    </Flex>
                  )}
                </div>
              )}
            </Content>

            {activeView === 'chat' && <Sider className="insightSider" width={320} breakpoint="xl" collapsedWidth={0}>
              <Segmented
                block
                options={[
                  { label: '洞察', value: 'insight' },
                  { label: '记忆', value: 'memory' },
                ]}
                value={panelMode}
                onChange={setPanelMode}
              />

              {panelMode === 'insight' ? (
                <Flex vertical gap={12} className="panelStack">
                  <Card size="small" title="当前主题">
                    <Paragraph className="panelText">{latestTopic}</Paragraph>
                  </Card>
                  <Card size="small" title="信号概览">
                    <Flex vertical gap={12}>
                      {signalMetrics.map((item) => (
                        <div key={item.label}>
                          <Flex justify="space-between">
                            <Text>{item.label}</Text>
                            <Text strong>{item.value}</Text>
                          </Flex>
                          <Progress percent={item.value} showInfo={false} strokeColor={item.color} />
                        </div>
                      ))}
                    </Flex>
                  </Card>
                  <Card size="small" title="执行状态">
                    <Flex gap={8}>
                      <Card size="small" className="miniStat">
                        <Text strong>{messages.filter((item) => item.role === 'assistant').length}</Text>
                        <Text type="secondary">回答</Text>
                      </Card>
                      <Card size="small" className="miniStat">
                        <Text strong>{lastSteps.length}</Text>
                        <Text type="secondary">步骤</Text>
                      </Card>
                      <Card size="small" className="miniStat">
                        <Text strong>{tools.web ? '开' : '关'}</Text>
                        <Text type="secondary">联网</Text>
                      </Card>
                    </Flex>
                  </Card>
                </Flex>
              ) : (
                <Flex vertical gap={12} className="panelStack">
                  <Card size="small" title="已关注话题">
                    <div className="memoryList">
                      {memories.map((item) => (
                        <div className="memoryRow" key={item.label}>
                          <div>
                            <Text strong>{item.label}</Text>
                            <Text type="secondary" className="blockText">
                              {item.status}
                            </Text>
                          </div>
                          <Tag color={item.score > 85 ? 'geekblue' : 'cyan'}>{item.score}</Tag>
                        </div>
                      ))}
                    </div>
                  </Card>
                  <Card size="small" title="记忆策略">
                    <Paragraph className="panelText">
                      默认只把用户明确要求关注的话题写入记忆，临时检索线索不会自动沉淀。
                    </Paragraph>
                  </Card>
                </Flex>
              )}
            </Sider>}
          </Layout>

          {activeView === 'chat' && <Card className="composerCard" variant="outlined">
            <Input.TextArea
              ref={inputRef}
              value={input}
              rows={2}
              placeholder="输入新闻、链接、话题或你的分析目标..."
              onChange={(event) => setInput(event.target.value)}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  sendMessage(input);
                }
              }}
            />
            <Flex align="center" justify="space-between" className="composerActions">
              <Space wrap>
                <Tooltip title="启用联网检索">
                  <Switch
                    checked={tools.web}
                    checkedChildren={<GlobalOutlined />}
                    unCheckedChildren={<GlobalOutlined />}
                    onChange={(checked) => setTools((value) => ({ ...value, web: checked }))}
                  />
                </Tooltip>
                <Tooltip title="启用话题记忆">
                  <Switch
                    checked={tools.memory}
                    checkedChildren={<StarOutlined />}
                    unCheckedChildren={<StarOutlined />}
                    onChange={(checked) => setTools((value) => ({ ...value, memory: checked }))}
                  />
                </Tooltip>
                <Tag icon={<BulbOutlined />} color="processing">
                  ReAct
                </Tag>
              </Space>
              <Space>
                <Tooltip title="清空输入">
                  <Button icon={<DeleteOutlined />} onClick={() => setInput('')} />
                </Tooltip>
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  loading={loading}
                  disabled={!input.trim()}
                  onClick={() => sendMessage(input)}
                />
              </Space>
            </Flex>
          </Card>}
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
