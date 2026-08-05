import React, { useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
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
  SendOutlined,
  StarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
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

const sessions = [
  { key: 'active', label: 'AI 搜索产品竞品动态', time: '09:42', icon: <ThunderboltOutlined /> },
  { key: 'policy', label: '短视频平台政策变化', time: '昨天', icon: <ClockCircleOutlined /> },
  { key: 'chip', label: '芯片出口管制追踪', time: '周一', icon: <ClockCircleOutlined /> },
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
          <Paragraph className="messageText">{message.content}</Paragraph>
          {!isUser && message.steps?.length > 0 && (
            <>
              <Divider className="compactDivider" />
              <div className="stepList">
                {message.steps.slice(0, 5).map((step, index) => (
                  <div className="stepItem" key={`${index}-${step.action || step.tool_name || 'step'}`}>
                    <Text type="secondary">Step {index + 1}</Text>
                    <Text code ellipsis>
                      {step.action || step.tool_name || step.final_answer || 'reasoning'}
                    </Text>
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
  const [userId] = useState(getOrCreateUserId);
  const inputRef = useRef(null);

  const latestTopic = useMemo(() => {
    const latest = [...messages].reverse().find((item) => item.role === 'user');
    return latest?.content || '等待新的分析任务';
  }, [messages]);

  function createNewChat() {
    setMessages([]);
    setInput('');
    setSessionId(null);
    setLastSteps([]);
    inputRef.current?.focus?.();
  }

  async function copyMessage(content) {
    await window.navigator.clipboard?.writeText(content);
  }

  async function sendMessage(text) {
    const message = text.trim();
    if (!message || loading) return;

    const nextMessages = [...messages, { role: 'user', content: message, at: new Date().toISOString() }];
    setMessages(nextMessages);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          user_id: userId,
          session_id: sessionId,
          history: messages.map(({ role, content }) => ({ role, content })),
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || '请求失败');
      }

      setSessionId(data.session_id);
      setLastSteps(data.steps || []);
      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: data.answer || '已完成，但后端没有返回具体回答。',
          completed: data.completed,
          steps: data.steps || [],
          at: new Date().toISOString(),
        },
      ]);
    } catch (error) {
      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: `请求失败：${error.message || '请确认后端服务已经启动，并检查网络连接。'}`,
          completed: false,
          error: true,
          at: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  const menuItems = [
    { key: 'chat', icon: <MessageOutlined />, label: '当前对话' },
    { key: 'memory', icon: <StarOutlined />, label: '话题记忆' },
    { key: 'history', icon: <ClockCircleOutlined />, label: '搜索记录' },
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
                <Text type="secondary">告别信息差</Text>
              </div>
            </Flex>

            <Button type="primary" block icon={<PlusOutlined />} onClick={createNewChat}>
              新建分析
            </Button>

            <Menu mode="inline" selectedKeys={['chat']} items={menuItems} className="navMenu" />

            <div className="siderSection">
              <Text type="secondary" className="sectionTitle">
                最近任务
              </Text>
              <div className="sessionList">
                {sessions.map((item) => (
                  <div className={item.key === 'active' ? 'sessionItem active' : 'sessionItem'} key={item.key}>
                    <Avatar size="small" icon={item.icon} />
                    <div className="sessionCopy">
                      <Text ellipsis strong={item.key === 'active'}>
                        {item.label}
                      </Text>
                      <Text type="secondary">{item.time}</Text>
                    </div>
                  </div>
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
              <Text strong>新对话</Text>
              <Text type="secondary">{sessionId ? `会话 ${sessionId.slice(0, 12)}` : '准备接收新的热点分析任务'}</Text>
            </Flex>
            <Space>
              <Button icon={<ExportOutlined />}>导出</Button>
              <Button type="primary" icon={<LoginOutlined />}>
                登录
              </Button>
            </Space>
          </Header>

          <Layout className="mainLayout">
            <Content className="conversationPane">
              {messages.length === 0 ? (
                <div className="emptyCanvas">
                  <PulseGraph />
                  <Flex vertical align="center" gap={6} className="heroCopy">
                    <Text className="heroEyebrow">Topic Pulse</Text>
                    <Title level={1}>把热点线索整理成可行动的判断。</Title>
                    <Paragraph>
                      输入新闻、话题或跟踪目标，系统会结合记忆、检索和 ReAct 推理返回分析结果。
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
                  {loading && (
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

            <Sider className="insightSider" width={320} breakpoint="xl" collapsedWidth={0}>
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
            </Sider>
          </Layout>

          <Card className="composerCard" variant="outlined">
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
          </Card>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

createRoot(document.getElementById('root')).render(<TopicPulseApp />);
