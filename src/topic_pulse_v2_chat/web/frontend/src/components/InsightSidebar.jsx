import React from 'react';
import { Card, Flex, Layout, Progress, Segmented, Tag, Typography } from 'antd';

const { Sider } = Layout;
const { Text, Paragraph } = Typography;

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

export default function InsightSidebar({ lastSteps, latestTopic, messages, panelMode, setPanelMode, tools }) {
  return (
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
  );
}
