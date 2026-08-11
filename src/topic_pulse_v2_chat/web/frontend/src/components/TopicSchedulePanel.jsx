import React, { useMemo, useState } from 'react';
import { Alert, Button, Empty, Flex, List, Modal, Select, Space, Spin, Tag, Typography } from 'antd';
import {
  ClockCircleOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import MarkdownView from './MarkdownView.jsx';

const { Text, Title } = Typography;

const scheduleOptions = [
  { value: 'interval_30', label: '每 30 分钟', payload: { trigger: 'interval', interval_minutes: 30 } },
  { value: 'interval_60', label: '每 1 小时', payload: { trigger: 'interval', interval_minutes: 60 } },
  { value: 'interval_360', label: '每 6 小时', payload: { trigger: 'interval', interval_minutes: 360 } },
  { value: 'cron_9_0', label: '每天 09:00', payload: { trigger: 'cron', interval_minutes: 60, cron_hour: 9, cron_minute: 0 } },
  { value: 'cron_18_0', label: '每天 18:00', payload: { trigger: 'cron', interval_minutes: 60, cron_hour: 18, cron_minute: 0 } },
];

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

function scheduleText(schedule) {
  if (!schedule) return '未配置';
  if (schedule.trigger === 'interval') {
    const minutes = schedule.trigger_args?.minutes;
    if (minutes === 30) return '每 30 分钟';
    if (minutes === 60) return '每 1 小时';
    if (minutes === 360) return '每 6 小时';
    return minutes ? `每 ${minutes} 分钟` : '间隔刷新';
  }
  if (schedule.trigger === 'cron') {
    const hour = String(schedule.trigger_args?.hour ?? 0).padStart(2, '0');
    const minute = String(schedule.trigger_args?.minute ?? 0).padStart(2, '0');
    return `每天 ${hour}:${minute}`;
  }
  return schedule.trigger;
}

function statusTag(schedule) {
  if (!schedule) return <Tag>未配置</Tag>;
  if (schedule.status === 'active') return <Tag color="green">运行中</Tag>;
  if (schedule.status === 'paused') return <Tag color="orange">已暂停</Tag>;
  return <Tag>{schedule.status}</Tag>;
}

function parseRunSummary(value) {
  if (!value) return '';
  try {
    const payload = JSON.parse(value);
    const parts = [];
    if (payload.topic_name) parts.push(`**${payload.topic_name}**`);
    if (Number.isFinite(Number(payload.new_count))) parts.push(`新增 ${payload.new_count} 条`);
    if (payload.summary) parts.push(payload.summary);
    return parts.join('\n\n') || value;
  } catch {
    return value;
  }
}

export default function TopicSchedulePanel({
  schedule,
  runs,
  loading,
  actionLoading,
  error,
  onCreate,
  onPause,
  onResume,
  onRun,
  onReload,
}) {
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedOption, setSelectedOption] = useState(scheduleOptions[1].value);
  const selectedPayload = useMemo(
    () => scheduleOptions.find((item) => item.value === selectedOption)?.payload || scheduleOptions[1].payload,
    [selectedOption],
  );

  async function confirmCreate() {
    await onCreate?.({ ...selectedPayload, enabled: true });
    setModalOpen(false);
  }

  return (
    <div className="topicSchedulePanel">
      <Flex align="center" justify="space-between" gap={12} className="topicScheduleHeader">
        <div>
          <Text className="heroEyebrow">Schedule</Text>
          <Title level={3}>定时刷新</Title>
          <Text type="secondary">针对当前关注话题自动拉取最新动态并写回本地记忆。</Text>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={onReload} loading={loading}>
            刷新状态
          </Button>
          {!schedule && (
            <Button type="primary" icon={<ClockCircleOutlined />} onClick={() => setModalOpen(true)}>
              创建任务
            </Button>
          )}
          {schedule && (
            <Button icon={<ThunderboltOutlined />} onClick={() => onRun?.(schedule.id)} loading={actionLoading === 'run'}>
              立即刷新
            </Button>
          )}
          {schedule?.status === 'active' && (
            <Button icon={<PauseCircleOutlined />} onClick={() => onPause?.(schedule.id)} loading={actionLoading === 'pause'}>
              暂停
            </Button>
          )}
          {schedule?.status === 'paused' && (
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => onResume?.(schedule.id)} loading={actionLoading === 'resume'}>
              恢复
            </Button>
          )}
        </Space>
      </Flex>

      {error && <Alert type="error" showIcon message={error} className="topicAlert" />}

      <div className="topicScheduleBody">
        {loading ? (
          <Flex align="center" gap={10} className="topicScheduleLoading">
            <Spin size="small" />
            <Text type="secondary">正在读取定时任务状态</Text>
          </Flex>
        ) : schedule ? (
          <div className="topicScheduleMeta">
            <div>
              <Text type="secondary">状态</Text>
              <div>{statusTag(schedule)}</div>
            </div>
            <div>
              <Text type="secondary">频率</Text>
              <Text strong>{scheduleText(schedule)}</Text>
            </div>
            <div>
              <Text type="secondary">任务</Text>
              <Text ellipsis>{schedule.name || schedule.id}</Text>
            </div>
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前话题还没有定时刷新任务" />
        )}

        {schedule && (
          <div className="topicRunList">
            <Flex align="center" justify="space-between">
              <Text strong>最近运行</Text>
              <Text type="secondary">{runs?.length || 0} 条记录</Text>
            </Flex>
            {runs?.length ? (
              <List
                size="small"
                dataSource={runs.slice(0, 5)}
                renderItem={(run) => (
                  <List.Item>
                    <div className="topicRunItem">
                      <Flex align="center" gap={8} wrap>
                        <Tag color={run.status === 'success' ? 'green' : run.status === 'failed' ? 'red' : 'blue'}>
                          {run.status}
                        </Tag>
                        <Text type="secondary">{formatDateTime(run.started_at)}</Text>
                        {run.duration_ms != null && <Text type="secondary">{Math.round(run.duration_ms)} ms</Text>}
                      </Flex>
                      {run.error ? (
                        <Text className="topicRunSummary">{run.error}</Text>
                      ) : (
                        <MarkdownView
                          content={parseRunSummary(run.result_summary) || '暂无摘要'}
                          className="topicRunMarkdown"
                        />
                      )}
                    </div>
                  </List.Item>
                )}
              />
            ) : (
              <Text type="secondary">暂无运行记录</Text>
            )}
          </div>
        )}
      </div>

      <Modal
        title="创建定时刷新任务"
        open={modalOpen}
        okText="创建"
        cancelText="取消"
        confirmLoading={actionLoading === 'create'}
        onOk={confirmCreate}
        onCancel={() => setModalOpen(false)}
      >
        <div className="scheduleModalBody">
          <Text type="secondary">选择刷新频率</Text>
          <Select value={selectedOption} options={scheduleOptions} onChange={setSelectedOption} className="scheduleSelect" />
        </div>
      </Modal>
    </div>
  );
}
