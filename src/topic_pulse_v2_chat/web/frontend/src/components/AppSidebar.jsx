import React from 'react';
import { Avatar, Button, Card, Flex, Layout, Menu, Typography } from 'antd';
import { ClockCircleOutlined, MessageOutlined, PlusOutlined, StarOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { formatSessionTime } from '../utils/chat.js';

const { Sider } = Layout;
const { Text } = Typography;

const menuItems = [
  { key: 'chat', icon: <MessageOutlined />, label: '当前对话' },
  { key: 'topics', icon: <StarOutlined />, label: '已关注话题' },
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
  userId,
}) {
  return (
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

        <Button type="primary" block icon={<PlusOutlined />} className="newChatButton" onClick={onCreateNewChat}>
          新建对话
        </Button>

        <Menu
          mode="inline"
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
                className={item.id === (routedSessionId || currentSessionId) ? 'sessionItem active' : 'sessionItem'}
                key={item.id}
                onClick={() => onNavigate(`/chat/${encodeURIComponent(item.id)}`)}
              >
                <Avatar size="small" icon={index === 0 ? <ThunderboltOutlined /> : <ClockCircleOutlined />} />
                <div className="sessionCopy">
                  <Text ellipsis strong={item.id === (routedSessionId || currentSessionId)}>
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
                {userId}
              </Text>
            </div>
          </Flex>
        </Card>
      </Flex>
    </Sider>
  );
}
