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
