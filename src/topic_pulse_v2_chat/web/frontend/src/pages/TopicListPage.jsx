import React from 'react';
import { Alert, Avatar, Button, Card, Empty, Flex, Space, Tag, Typography } from 'antd';
import { FileMarkdownOutlined, ReloadOutlined, RightOutlined } from '@ant-design/icons';

const { Text, Title, Paragraph } = Typography;

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

export default function TopicListPage({ topics, loading, error, onReload, onSelectTopic }) {
  return (
    <div className="topicPage">
      <Flex align="center" justify="space-between" className="topicPageHeader">
        <div>
          <Text className="heroEyebrow">Topic Memory</Text>
          <Title level={2}>已关注话题</Title>
          <Text type="secondary">读取 data/topics 目录下的 Markdown 文件，按更新时间展示。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={onReload} loading={loading}>
          刷新
        </Button>
      </Flex>

      {error && <Alert type="error" showIcon message={error} className="topicAlert" />}

      {topics.length === 0 && !loading ? (
        <Card className="topicEmptyCard">
          <Empty description="data/topics 目录下暂无话题 Markdown" />
        </Card>
      ) : (
        <div className="topicListGrid">
          {topics.map((topic) => (
            <Card
              hoverable
              className="topicListCard"
              key={topic.id}
              loading={loading}
              onClick={() => onSelectTopic(topic)}
            >
              <Flex align="flex-start" gap={14}>
                <Avatar className="topicFileAvatar" icon={<FileMarkdownOutlined />} />
                <div className="topicListBody">
                  <Flex align="center" justify="space-between" gap={12}>
                    <Title level={4}>{topic.title}</Title>
                    <RightOutlined className="topicCardArrow" />
                  </Flex>
                  <Paragraph ellipsis={{ rows: 2 }}>{topic.preview || '暂无摘要，点击查看完整 Markdown 内容。'}</Paragraph>
                  <Space wrap size={[8, 6]}>
                    <Tag color="geekblue">{topic.filename}</Tag>
                    <Tag color="cyan">{formatTopicDate(topic.updated_at)}</Tag>
                    <Tag>{Math.ceil(topic.size / 1024)} KB</Tag>
                  </Space>
                </div>
              </Flex>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
