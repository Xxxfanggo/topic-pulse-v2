export async function readApiResponse(response, fallbackMessage = 'Request failed') {
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

export function getAuthToken() {
  return window.localStorage.getItem('topic_pulse_access_token') || '';
}

export function setAuthSession(payload) {
  window.localStorage.setItem('topic_pulse_access_token', payload.access_token || '');
  window.localStorage.setItem('topic_pulse_auth_user', JSON.stringify(payload.user || null));
}

export function clearAuthSession() {
  window.localStorage.removeItem('topic_pulse_access_token');
  window.localStorage.removeItem('topic_pulse_auth_user');
}

export function getStoredAuthUser() {
  try {
    return JSON.parse(window.localStorage.getItem('topic_pulse_auth_user') || 'null');
  } catch {
    return null;
  }
}

export function authHeaders(headers = {}) {
  const token = getAuthToken();
  return token ? { ...headers, Authorization: `Bearer ${token}` } : headers;
}

export function authorizedFetch(url, options = {}) {
  return fetch(url, {
    ...options,
    headers: authHeaders(options.headers || {}),
  });
}

async function requestJson(url, options = {}, fallbackMessage = 'Request failed') {
  const response = await authorizedFetch(url, options);
  return readApiResponse(response, fallbackMessage);
}

export function requestRegistrationCode(email) {
  return requestJson(
    '/api/auth/register/request-code',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    },
    'Verification code request failed',
  );
}

export function verifyRegistration(payload) {
  return requestJson(
    '/api/auth/register/verify',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    'Registration failed',
  );
}

export function loginWithEmail(payload) {
  return requestJson(
    '/api/auth/login',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    'Login failed',
  );
}

export function getCurrentUser() {
  return requestJson('/api/auth/me', {}, 'Auth session expired');
}

export function getTodayHotspots(limit = 10) {
  return requestJson(`/api/hotspots/today?limit=${encodeURIComponent(limit)}`, {}, '今日热点加载失败');
}

export function getTopicSchedule(topicId) {
  return requestJson(`/api/topics/${encodeURIComponent(topicId)}/schedule`, {}, 'Schedule load failed');
}

export function createTopicSchedule(topicId, payload) {
  return requestJson(
    `/api/topics/${encodeURIComponent(topicId)}/schedule`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    'Schedule create failed',
  );
}

export function pauseSchedulerJob(jobId) {
  return requestJson(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/pause`, { method: 'POST' }, 'Schedule pause failed');
}

export function resumeSchedulerJob(jobId) {
  return requestJson(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/resume`, { method: 'POST' }, 'Schedule resume failed');
}

export function runSchedulerJob(jobId) {
  return requestJson(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/run`, { method: 'POST' }, 'Schedule run failed');
}

export function getSchedulerJobRuns(jobId) {
  return requestJson(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/runs`, {}, 'Run history load failed');
}
