import React from 'react';
import { Button, Card, Flex, Input, Space, Switch, Tag, Tooltip } from 'antd';
import { BulbOutlined, DeleteOutlined, GlobalOutlined, SendOutlined, StarOutlined } from '@ant-design/icons';

export default function ChatComposer({
  input,
  inputRef,
  loading,
  onInputChange,
  onSend,
  setTools,
  tools,
}) {
  return (
    <Card className="composerCard" variant="outlined">
      <Input.TextArea
        ref={inputRef}
        value={input}
        rows={2}
        placeholder="输入新闻、链接、话题或你的分析目标..."
        onChange={(event) => onInputChange(event.target.value)}
        onPressEnter={(event) => {
          if (!event.shiftKey) {
            event.preventDefault();
            onSend(input);
          }
        }}
      />
      <Flex align="center" justify="space-between" className="composerActions">
        <Space wrap>
          <Tooltip title="启用联网检索">
            <Switch
              checked={tools.web}
              checkedChildren={<GlobalOutlined />}
              unCheckedChildren={<GlobalOutlined />}
              onChange={(checked) => setTools((value) => ({ ...value, web: checked }))}
            />
          </Tooltip>
          <Tooltip title="启用话题记忆">
            <Switch
              checked={tools.memory}
              checkedChildren={<StarOutlined />}
              unCheckedChildren={<StarOutlined />}
              onChange={(checked) => setTools((value) => ({ ...value, memory: checked }))}
            />
          </Tooltip>
          <Tag icon={<BulbOutlined />} color="processing">
            ReAct
          </Tag>
        </Space>
        <Space>
          <Tooltip title="清空输入">
            <Button icon={<DeleteOutlined />} onClick={() => onInputChange('')} />
          </Tooltip>
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={loading}
            disabled={!input.trim()}
            onClick={() => onSend(input)}
          />
        </Space>
      </Flex>
    </Card>
  );
}
