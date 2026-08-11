const STORAGE_KEY = 'topic_pulse_user_id';

export function getOrCreateUserId() {
  const existing = window.localStorage.getItem(STORAGE_KEY);
  if (existing) return existing;
  const generated =
    window.crypto?.randomUUID?.() || `anonymous-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  window.localStorage.setItem(STORAGE_KEY, generated);
  return generated;
}

export function formatSessionTime(value) {
  if (!value) return '刚刚';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '刚刚';
  const diffMs = Date.now() - date.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diffMs < minute) return '刚刚';
  if (diffMs < hour) return `${Math.max(1, Math.floor(diffMs / minute))} 分钟前`;
  if (diffMs < day) return `${Math.floor(diffMs / hour)} 小时前`;
  if (diffMs < 2 * day) return '昨天';
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

export function formatMessageTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';

  const now = new Date();
  const isSameYear = date.getFullYear() === now.getFullYear();
  const isSameDay = date.toDateString() === now.toDateString();
  const timeText = date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });

  if (isSameDay) {
    return `今天 ${timeText}`;
  }

  const dateText = date.toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    ...(isSameYear ? {} : { year: 'numeric' }),
  });
  return `${dateText} ${timeText}`;
}

export function mergeAgentStep(steps = [], step = {}) {
  const key = `${step.step_index || steps.length + 1}-${step.title || step.tool_name || ''}`;
  const nextStep = { ...step, key };
  const index = steps.findIndex((item) => item.key === key);
  if (index === -1) {
    return [...steps, nextStep];
  }
  return steps.map((item, itemIndex) => (itemIndex === index ? { ...item, ...nextStep } : item));
}
