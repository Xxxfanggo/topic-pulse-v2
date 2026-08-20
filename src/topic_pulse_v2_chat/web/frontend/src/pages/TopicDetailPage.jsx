import React from 'react';
import { Button, Card, Flex, Skeleton, Tag, Typography } from 'antd';
import { ArrowLeftOutlined, CalendarOutlined } from '@ant-design/icons';
import MarkdownView from '../components/MarkdownView.jsx';
import TopicNotificationPanel from '../components/TopicNotificationPanel.jsx';
import TopicSchedulePanel from '../components/TopicSchedulePanel.jsx';

const { Text, Title } = Typography;

function formatTopicDate(value) {
  if (!value) return '未知时间';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function TopicDetailPage({
  topic,
  loading,
  schedule,
  scheduleRuns,
  scheduleLoading,
  scheduleActionLoading,
  scheduleError,
  notification,
  notificationDeliveries,
  notificationLoading,
  notificationSaving,
  notificationError,
  onBack,
  onCreateSchedule,
  onPauseSchedule,
  onResumeSchedule,
  onRunSchedule,
  onReloadSchedule,
  onToggleEmailNotification,
  isGuest,
}) {
  return (
    <div className="topicPage topicDetailPage">
      <div className="topicDetailHero">
        <Button type="text" className="topicBackButton" icon={<ArrowLeftOutlined />} onClick={onBack}>
          返回话题列表
        </Button>
        <Flex align="flex-end" justify="space-between" gap={16} className="topicDetailTitleRow">
          <div>
            <Text className="heroEyebrow">Topic Detail</Text>
            <Title level={2}>{topic?.title || '加载话题详情'}</Title>
            <Text type="secondary">{topic?.filename || '正在读取 Markdown 文件'}</Text>
          </div>
          {topic?.updated_at && (
            <Tag icon={<CalendarOutlined />} color="geekblue">
              {formatTopicDate(topic.updated_at)}
            </Tag>
          )}
        </Flex>
      </div>

      <TopicSchedulePanel
        schedule={schedule}
        runs={scheduleRuns}
        loading={scheduleLoading}
        actionLoading={scheduleActionLoading}
        error={scheduleError}
        onCreate={onCreateSchedule}
        onPause={onPauseSchedule}
        onResume={onResumeSchedule}
        onRun={onRunSchedule}
        onReload={onReloadSchedule}
        disabled={isGuest}
      />

      <TopicNotificationPanel
        subscription={notification}
        deliveries={notificationDeliveries}
        loading={notificationLoading}
        saving={notificationSaving}
        error={notificationError}
        onToggleEmail={onToggleEmailNotification}
        disabled={isGuest}
      />

      <Card className="topicDetailCard" loading={loading && !!topic}>
        {loading && !topic ? <Skeleton active paragraph={{ rows: 8 }} /> : <MarkdownView content={topic?.content || ''} />}
      </Card>
    </div>
  );
}
