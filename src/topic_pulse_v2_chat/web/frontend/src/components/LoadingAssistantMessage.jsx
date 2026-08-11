import React from 'react';
import { Avatar, Badge, Card, Flex, Typography } from 'antd';

const { Text } = Typography;

export default function LoadingAssistantMessage() {
  return (
    <Flex className="chatMessage isAssistant" gap={12}>
      <Avatar className="messageAvatar">TP</Avatar>
      <div className="messageMain">
        <Flex align="center" gap={8} className="messageMeta">
          <Text strong>Topic Pulse</Text>
          <Badge status="processing" text="推理中" />
        </Flex>
        <Card size="small" className="bubbleCard loadingCard">
          <span />
          <span />
          <span />
        </Card>
      </div>
    </Flex>
  );
}
