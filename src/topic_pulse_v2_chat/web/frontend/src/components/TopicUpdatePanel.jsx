import React, { useState } from 'react';
import { Tag, Typography } from 'antd';
import { RightOutlined, StarOutlined } from '@ant-design/icons';

const { Text } = Typography;

function normalizeTopicItems(items) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (typeof item === 'string') {
        return {
          date: '',
          title: item.trim(),
          source: '',
          url: '',
          summary: '',
        };
      }
      return {
        date: String(item?.date || '').trim(),
        title: String(item?.title || '').trim(),
        source: String(item?.source || '').trim(),
        url: String(item?.url || '').trim(),
        summary: String(item?.summary || '').trim(),
      };
    })
    .filter((item) => item.title);
}

export default function TopicUpdatePanel({ update }) {
  const [expanded, setExpanded] = useState(false);
  if (!update || !update.topic_name) return null;

  const newItems = normalizeTopicItems(update.new_items);
  const existingItems = normalizeTopicItems(update.existing_items);
  const initialItems = normalizeTopicItems(update.initial_items);
  const isCreated = update.status === 'created' || update.operation === 'create';
  const visibleInitialItems = initialItems.length > 0 ? initialItems : newItems;
  const initialCount = Number(update.initial_count || visibleInitialItems.length || 0);
  const newCount = isCreated ? 0 : Number(update.new_count || newItems.length || 0);
  const existingCount = Number(update.existing_count || existingItems.length || 0);
  const hasInitial = isCreated && initialCount > 0;
  const hasNew = !isCreated && newCount > 0;
  const statusText = hasInitial
    ? `已创建话题，写入 ${initialCount} 条初始记录`
    : hasNew
    ? `本次发现 ${newCount} 条新信息`
    : '本次未发现新增信息';

  return (
    <div
      className={`topicUpdatePanel ${expanded ? 'isExpanded' : ''} ${hasNew ? 'hasNew' : 'noNew'} ${
        isCreated ? 'isCreated' : ''
      }`}
    >
      <button type="button" className="topicUpdateToggle" onClick={() => setExpanded((value) => !value)}>
        <StarOutlined />
        <span>{update.topic_name}：{statusText}</span>
        {existingCount > 0 && <Tag color="default">已有 {existingCount}</Tag>}
        <RightOutlined className="referenceChevron" />
      </button>
      {expanded && (
        <div className="topicUpdateBody">
          {hasInitial && (
            <div className="topicUpdateGroup">
              <Text strong>初始记录</Text>
              <div className="topicUpdateList">
                {visibleInitialItems.slice(0, 6).map((item, index) => (
                  <div className="topicUpdateItem isInitial" key={`${item.url || item.title}-${index}`}>
                    <Tag color="processing">初始</Tag>
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
          {!isCreated && newItems.length > 0 && (
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
