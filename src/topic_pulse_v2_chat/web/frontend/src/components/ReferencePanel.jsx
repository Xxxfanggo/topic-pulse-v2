import React, { useState } from 'react';
import { Typography } from 'antd';
import { GlobalOutlined, RightOutlined } from '@ant-design/icons';

const { Text } = Typography;

function normalizeReferenceData(referenceData) {
  if (!Array.isArray(referenceData)) return [];
  const seen = new Set();
  return referenceData
    .map((item) => {
      const title = item?.title || '';
      const link = item?.url || item?.link || '';
      return {
        title: String(title).trim(),
        link: String(link).trim(),
      };
    })
    .filter((item) => {
      if (!item.title || !item.link || seen.has(item.link)) return false;
      seen.add(item.link);
      return true;
    });
}

export default function ReferencePanel({ queryKey, referenceData }) {
  const [expanded, setExpanded] = useState(false);
  const references = normalizeReferenceData(referenceData);
  const keywordText = String(queryKey || '').trim();
  if (!keywordText && references.length === 0) return null;

  return (
    <div className={`referencePanel ${expanded ? 'isExpanded' : ''}`}>
      <button type="button" className="referenceToggle" onClick={() => setExpanded((value) => !value)}>
        <GlobalOutlined />
        <span>搜索 {keywordText ? 1 : 0} 个关键词，参考 {references.length} 篇资料</span>
        <RightOutlined className="referenceChevron" />
      </button>
      {expanded && (
        <div className="referenceBody">
          {keywordText && <Text className="referenceQuery">“{keywordText}”</Text>}
          {references.length > 0 && (
            <ol className="referenceList">
              {references.slice(0, 18).map((reference, index) => (
                <li key={`${reference.link}-${index}`}>
                  <a href={reference.link} target="_blank" rel="noreferrer">
                    {reference.title}
                  </a>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
