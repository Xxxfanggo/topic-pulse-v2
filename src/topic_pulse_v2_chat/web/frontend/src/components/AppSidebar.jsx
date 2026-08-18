import React from 'react';
import { Avatar, Button, Card, Flex, Layout, Menu, Tooltip, Typography } from 'antd';
import { ClockCircleOutlined, MessageOutlined, PlusOutlined, StarOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { formatSessionTime } from '../utils/chat.js';

const { Sider } = Layout;
const { Text } = Typography;

const menuItems = [
  { key: 'chat', icon: <MessageOutlined />, label: '当前对话', title: '当前对话' },
  { key: 'topics', icon: <StarOutlined />, label: '已关注话题', title: '已关注话题' },
];

export default function AppSidebar({
  activeView,
  chatSessions,
  collapsed,
  currentSessionId,
  onCreateNewChat,
  onNavigate,
  routedSessionId,
  sessionsError,
  sessionsLoading,
  sessionLimit,
  userId,
  isGuest,
}) {
  return (
    <Sider className={`appSider ${collapsed ? 'isCollapsed' : ''}`} width={280} collapsedWidth={72} collapsed={collapsed} trigger={null}>
      <Flex vertical gap={16} className="siderInner">
        <Tooltip title={collapsed ? 'Topic Pulse' : ''} placement="right">
          <Flex align="center" gap={12} className="brand">
            <Avatar shape="square" className="brandAvatar">
              TP
            </Avatar>
            <div className="brandCopy">
              <Text strong>Topic Pulse</Text>
              <Text type="secondary">告别信息焦虑~</Text>
            </div>
          </Flex>
        </Tooltip>

        <Tooltip title={collapsed ? '新建对话' : ''} placement="right">
          <Button type="primary" block icon={<PlusOutlined />} className="newChatButton" onClick={onCreateNewChat} aria-label="新建对话">
            {collapsed ? null : '新建对话'}
          </Button>
        </Tooltip>

        <Menu
          mode="inline"
          inlineCollapsed={collapsed}
          selectedKeys={[activeView === 'topics' ? 'topics' : 'chat']}
          items={menuItems}
          className="navMenu"
          onClick={({ key }) => {
            if (key === 'topics') {
              onNavigate('/topics');
            } else {
              onNavigate('/chat');
            }
          }}
        />

        <div className="siderSection">
          <Text type="secondary" className="sectionTitle">
            最近会话
            {sessionLimit ? `（${chatSessions.length}/${sessionLimit}）` : ''}
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
              <Tooltip title={collapsed ? item.title : ''} placement="right" key={item.id}>
                <button
                  type="button"
                  className={item.id === (routedSessionId || currentSessionId) ? 'sessionItem active' : 'sessionItem'}
                  onClick={() => onNavigate(`/chat/${encodeURIComponent(item.id)}`)}
                  aria-label={item.title}
                >
                  <Avatar size="small" icon={index === 0 ? <ThunderboltOutlined /> : <ClockCircleOutlined />} />
                  <div className="sessionCopy">
                    <Text ellipsis strong={item.id === (routedSessionId || currentSessionId)}>
                      {item.title}
                    </Text>
                    <Text type="secondary">{formatSessionTime(item.updated_at)}</Text>
                  </div>
                </button>
              </Tooltip>
            ))}
          </div>
        </div>

        <Tooltip title={collapsed ? (isGuest ? '访客模式' : '已登录') : ''} placement="right">
          <Card size="small" className="visitorCard">
            <Flex align="center" gap={10}>
              <Avatar>{userId?.slice(0, 1).toUpperCase() || 'U'}</Avatar>
              <div className="visitorCopy">
                <Text strong>{isGuest ? '访客模式' : '已登录'}</Text>
                <Text type="secondary" className="blockText">
                  {isGuest ? userId?.replace('@guest.local', '') : userId}
                </Text>
              </div>
            </Flex>
          </Card>
        </Tooltip>
      </Flex>
    </Sider>
  );
}
