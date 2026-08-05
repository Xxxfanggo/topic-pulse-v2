import React from 'react';
import { Button, Card, Flex, Skeleton, Tag, Typography } from 'antd';
import { ArrowLeftOutlined, CalendarOutlined } from '@ant-design/icons';

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

function MarkdownView({ content }) {
  const blocks = content.split(/\r?\n/);

  return (
    <article className="markdownView">
      {blocks.map((line, index) => {
        const trimmed = line.trim();
        const key = `${index}-${trimmed.slice(0, 16)}`;

        if (!trimmed) {
          return <div className="markdownGap" key={key} />;
        }

        if (trimmed.startsWith('### ')) {
          return <h3 key={key}>{trimmed.slice(4)}</h3>;
        }

        if (trimmed.startsWith('## ')) {
          return <h2 key={key}>{trimmed.slice(3)}</h2>;
        }

        if (trimmed.startsWith('# ')) {
          return <h1 key={key}>{trimmed.slice(2)}</h1>;
        }

        if (trimmed.startsWith('- ')) {
          const text = trimmed.slice(2);
          const urlMatch = text.match(/(https?:\/\/\S+)/);
          return (
            <div className="markdownBullet" key={key}>
              <span />
              <p>
                {urlMatch ? (
                  <>
                    {text.slice(0, urlMatch.index)}
                    <a href={urlMatch[0]} target="_blank" rel="noreferrer">
                      {urlMatch[0]}
                    </a>
                    {text.slice((urlMatch.index || 0) + urlMatch[0].length)}
                  </>
                ) : (
                  text
                )}
              </p>
            </div>
          );
        }

        return <p key={key}>{trimmed}</p>;
      })}
    </article>
  );
}

export default function TopicDetailPage({ topic, loading, onBack }) {
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

      <Card className="topicDetailCard" loading={loading && !!topic}>
        {loading && !topic ? <Skeleton active paragraph={{ rows: 8 }} /> : <MarkdownView content={topic?.content || ''} />}
      </Card>
    </div>
  );
}
