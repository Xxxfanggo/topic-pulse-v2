import React from 'react';
import { Card, Flex, Tag, Typography } from 'antd';
import PulseGraph from './PulseGraph.jsx';

const { Title, Paragraph, Text } = Typography;

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

export default function EmptyChatCanvas({ onPrompt }) {
  return (
    <div className="emptyCanvas">
      <PulseGraph />
      <Flex vertical align="center" gap={6} className="heroCopy">
        <Text className="heroEyebrow">Topic Pulse</Text>
        <Title level={1}>把热点线索整理成可行动的判断。</Title>
        <Paragraph>
          输入新闻、话题或追踪目标，系统会结合记忆、检索和 ReAct 推理返回分析结果。
        </Paragraph>
      </Flex>
      <div className="promptGrid">
        {starterPrompts.map((item) => (
          <Card
            key={item.title}
            hoverable
            className="promptCard"
            onClick={() => onPrompt(item.prompt)}
          >
            <Tag color="geekblue">{item.label}</Tag>
            <Title level={5}>{item.title}</Title>
            <Paragraph ellipsis={{ rows: 2 }}>{item.prompt}</Paragraph>
          </Card>
        ))}
      </div>
    </div>
  );
}
