export async function readApiResponse(response, fallbackMessage = '请求失败') {
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.toLowerCase().includes('application/json');
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload !== null
        ? payload.detail || payload.message || fallbackMessage
        : payload || fallbackMessage;
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  return payload;
}

async function requestJson(url, options = {}, fallbackMessage = '请求失败') {
  const response = await fetch(url, options);
  return readApiResponse(response, fallbackMessage);
}

export function getTopicSchedule(topicId) {
  return requestJson(`/api/topics/${encodeURIComponent(topicId)}/schedule`, {}, '定时任务加载失败');
}

export function createTopicSchedule(topicId, payload) {
  return requestJson(
    `/api/topics/${encodeURIComponent(topicId)}/schedule`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '定时任务创建失败',
  );
}

export function pauseSchedulerJob(jobId) {
  return requestJson(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/pause`, { method: 'POST' }, '定时任务暂停失败');
}

export function resumeSchedulerJob(jobId) {
  return requestJson(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/resume`, { method: 'POST' }, '定时任务恢复失败');
}

export function runSchedulerJob(jobId) {
  return requestJson(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/run`, { method: 'POST' }, '定时任务运行失败');
}

export function getSchedulerJobRuns(jobId) {
  return requestJson(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/runs`, {}, '运行记录加载失败');
}
