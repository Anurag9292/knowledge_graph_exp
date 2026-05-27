const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// Graphs
export const graphsApi = {
  list: () => request<any[]>('/api/graphs'),
  get: (id: string) => request<any>(`/api/graphs/${id}`),
  create: (data: any) => request<any>('/api/graphs', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: any) => request<any>(`/api/graphs/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/api/graphs/${id}`, { method: 'DELETE' }),
  validate: (id: string) => request<any>(`/api/graphs/${id}/validate`, { method: 'POST' }),
};

// Experiments
export const experimentsApi = {
  list: () => request<any[]>('/api/experiments'),
  get: (id: string) => request<any>(`/api/experiments/${id}`),
  create: (data: any) => request<any>('/api/experiments', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: any) => request<any>(`/api/experiments/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/api/experiments/${id}`, { method: 'DELETE' }),
  createRun: (sessionId: string) => request<any>(`/api/experiments/${sessionId}/runs`, { method: 'POST' }),
  listRuns: (sessionId: string) => request<any[]>(`/api/experiments/${sessionId}/runs`),
  getRun: (sessionId: string, runId: string) => request<any>(`/api/experiments/${sessionId}/runs/${runId}`),
  pauseRun: (sessionId: string, runId: string) => request<any>(`/api/experiments/${sessionId}/runs/${runId}/pause`, { method: 'POST' }),
  resumeRun: (sessionId: string, runId: string) => request<any>(`/api/experiments/${sessionId}/runs/${runId}/resume`, { method: 'POST' }),
  cancelRun: (sessionId: string, runId: string) => request<any>(`/api/experiments/${sessionId}/runs/${runId}/cancel`, { method: 'POST' }),
};

// Agents
export const agentsApi = {
  listTypes: () => request<any[]>('/api/agents/types'),
  getType: (id: string) => request<any>(`/api/agents/types/${id}`),
  createType: (data: any) => request<any>('/api/agents/types', { method: 'POST', body: JSON.stringify(data) }),
  updateType: (id: string, data: any) => request<any>(`/api/agents/types/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteType: (id: string) => request<void>(`/api/agents/types/${id}`, { method: 'DELETE' }),
};

// Documents
export const documentsApi = {
  upload: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/documents/upload`, { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Upload failed');
    return res.json();
  },
  parseText: (text: string) => request<any>('/api/documents/parse-text', { method: 'POST', body: JSON.stringify({ text }) }),
  formats: () => request<any[]>('/api/documents/formats'),
};

// Evals
export const evalsApi = {
  listConfigs: () => request<any[]>('/api/evals/configs'),
  createConfig: (data: any) => request<any>('/api/evals/configs', { method: 'POST', body: JSON.stringify(data) }),
  runEval: (data: any) => request<any>('/api/evals/run', { method: 'POST', body: JSON.stringify(data) }),
  getResults: (runId: string) => request<any[]>(`/api/evals/results/${runId}`),
};
