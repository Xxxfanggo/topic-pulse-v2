import React from 'react';
import { Avatar, Button, Card, Divider, Flex, Tag, Tooltip, Typography } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import MarkdownView from './MarkdownView.jsx';
import ReferencePanel from './ReferencePanel.jsx';
import TopicUpdatePanel from './TopicUpdatePanel.jsx';
import { formatMessageTime } from '../utils/chat.js';

const { Text, Paragraph } = Typography;

export default function MessageBubble({ message, onCopy }) {
  const isUser = message.role === 'user';
  const messageTime = formatMessageTime(message.at || message.created_at);

  return (
    <Flex className={`chatMessage ${isUser ? 'isUser' : 'isAssistant'} ${message.error ? 'isError' : ''}`} gap={12}>
      <Avatar className="messageAvatar">{isUser ? '你' : 'TP'}</Avatar>
      <div className="messageMain">
        <Flex align="center" gap={8} className="messageMeta">
          <Text strong>{isUser ? '你' : 'Topic Pulse'}</Text>
          {messageTime && (
            <Text type="secondary" className="messageTime">
              {messageTime}
            </Text>
          )}
          {!isUser && message.completed === false && <Tag color="warning">未完成</Tag>}
        </Flex>
        <Card size="small" className="bubbleCard">
          {!isUser && !message.error && (
            <>
              <TopicUpdatePanel update={message.topic_update} />
              <ReferencePanel queryKey={message.query_key} referenceData={message.reference_data} />
            </>
          )}
          {!isUser && message.status && !message.content && (
            <Text type="secondary" className="messageStatus">
              <span className="statusSpinner" aria-hidden="true" />
              {message.status}
            </Text>
          )}
          {isUser || message.error ? (
            <Paragraph className="messageText">{message.content}</Paragraph>
          ) : (
            <MarkdownView content={message.content} className="messageMarkdown" />
          )}
          {!isUser && message.steps?.length > 0 && (
            <>
              <Divider className="compactDivider" />
              <div className="stepList">
                {message.steps.slice(0, 5).map((step, index) => (
                  <div className={`stepItem ${step.status ? `is-${step.status}` : ''}`} key={step.key || `${index}-${step.action || step.tool_name || 'step'}`}>
                    <span className="stepDot" />
                    <div className="stepCopy">
                      <Text strong>{step.title || `Step ${index + 1}`}</Text>
                      <Text type="secondary">
                        {step.detail || step.thought || step.action || step.tool_name || step.final_answer || '正在整理推理步骤'}
                      </Text>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
        <Tooltip title="复制消息">
          <Button size="small" type="text" icon={<CopyOutlined />} onClick={() => onCopy(message.content)} />
        </Tooltip>
      </div>
    </Flex>
  );
}
