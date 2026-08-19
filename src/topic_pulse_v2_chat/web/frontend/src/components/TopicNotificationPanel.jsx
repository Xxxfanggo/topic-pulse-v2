import React from 'react';
import { Alert, Flex, List, Spin, Switch, Tag, Typography } from 'antd';
import { MailOutlined } from '@ant-design/icons';

const { Text, Title } = Typography;

function formatDateTime(value) {
  if (!value) return '暂无';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusColor(status) {
  if (status === 'sent') return 'green';
  if (status === 'failed') return 'red';
  if (status === 'skipped') return 'orange';
  return 'blue';
}

export default function TopicNotificationPanel({
  subscription,
  deliveries,
  loading,
  saving,
  error,
  onToggleEmail,
  disabled = false,
}) {
  const enabled = Boolean(subscription?.enabled);
  return (
    <div className="topicNotificationPanel">
      <Flex align="center" justify="space-between" gap={12} className="topicNotificationHeader">
        <div>
          <Text className="heroEyebrow">Notification</Text>
          <Title level={3}>Email 推送</Title>
          <Text type="secondary">当定时刷新发现新增动态时，发送摘要到账号邮箱。</Text>
        </div>
        <Flex align="center" gap={10}>
          <MailOutlined className="topicNotificationIcon" />
          <Switch
            checked={enabled}
            loading={saving}
            disabled={disabled || loading}
            onChange={(checked) => onToggleEmail?.(checked)}
          />
        </Flex>
      </Flex>

      {disabled && <Alert type="info" showIcon message="访客模式不能开启 Email 推送，登录后可使用。" className="topicAlert" />}
      {error && <Alert type="error" showIcon message={error} className="topicAlert" />}

      {loading ? (
        <Flex align="center" gap={10} className="topicNotificationLoading">
          <Spin size="small" />
          <Text type="secondary">正在读取通知状态</Text>
        </Flex>
      ) : (
        <div className="topicNotificationBody">
          <div className="topicNotificationMeta">
            <div>
              <Text type="secondary">收件邮箱</Text>
              <Text strong ellipsis>{subscription?.target || '未设置'}</Text>
            </div>
            <div>
              <Text type="secondary">发送规则</Text>
              <Text>{subscription?.only_when_has_new !== false ? `新增不少于 ${subscription?.min_new_count || 1} 条` : '每次刷新后发送'}</Text>
            </div>
            <div>
              <Text type="secondary">状态</Text>
              <Tag color={enabled ? 'green' : undefined}>{enabled ? '已开启' : '未开启'}</Tag>
            </div>
          </div>

          <div className="topicDeliveryList">
            <Flex align="center" justify="space-between">
              <Text strong>最近投递</Text>
              <Text type="secondary">{deliveries?.length || 0} 条记录</Text>
            </Flex>
            {deliveries?.length ? (
              <List
                size="small"
                dataSource={deliveries.slice(0, 5)}
                renderItem={(delivery) => (
                  <List.Item>
                    <div className="topicDeliveryItem">
                      <Flex align="center" gap={8} wrap>
                        <Tag color={statusColor(delivery.status)}>{delivery.status}</Tag>
                        <Text type="secondary">{formatDateTime(delivery.sent_at || delivery.created_at)}</Text>
                      </Flex>
                      <Text className="topicRunSummary">{delivery.error || delivery.subject || '暂无摘要'}</Text>
                    </div>
                  </List.Item>
                )}
              />
            ) : (
              <Text type="secondary">暂无投递记录</Text>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
