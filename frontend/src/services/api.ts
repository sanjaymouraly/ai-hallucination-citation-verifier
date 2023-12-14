import type { AnalysisDetail, AnalysisSummary, DashboardData, ProviderPreset, ProviderSettings, ReviewQueueItem } from '../types';

const API = '/api';

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const token = sessionStorage.getItem('verity_token');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  let response: Response;
  try { response = await fetch(`${API}${path}`, { ...init, headers }); }
  catch { throw new Error('Could not reach Verity. Check that the API is running and retry.'); }
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      const value = body?.detail;
      detail = typeof value === 'string' ? value : Array.isArray(value) ? value.map((item: { msg?: string }) => item.msg).filter(Boolean).join('; ') : detail;
    } catch { /* use generic status */ }
    const error = new Error(detail) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  const type = response.headers.get('content-type') || '';
  if (type.includes('application/json')) return response.json() as Promise<T>;
  return response as T;
}

export const api = {
  authStatus: () => request<{ required: boolean; owner?: string | null }>('/auth/status'),
  dashboard: () => request<DashboardData>('/dashboard'),
  analyses: (params = '') => request<{ items: AnalysisSummary[]; total: number; offset: number; limit: number }>(`/analyses${params}`),
  analysis: (id: string) => request<AnalysisDetail>(`/analyses/${id}`),
  createAnalysis: (body: unknown) => request<AnalysisSummary>('/analyses', { method: 'POST', body: JSON.stringify(body) }),
  createUpload: (form: FormData) => request<AnalysisSummary>('/analyses/upload', { method: 'POST', body: form }),
  createBatch: (body: unknown) => request<{ batch_id: string; total: number; items: AnalysisSummary[] }>('/batches', { method: 'POST', body: JSON.stringify(body) }),
  batch: (id: string) => request<{ batch_id: string; total: number; complete: boolean; counts: Record<string, number>; items: AnalysisSummary[] }>(`/batches/${id}`),
  reviewQueue: (status = 'needs_human_review') => request<{ items: ReviewQueueItem[]; total: number }>(`/reviews?status=${encodeURIComponent(status)}`),
  addReview: (id: string, body: unknown) => request(`/claims/${id}/reviews`, { method: 'POST', body: JSON.stringify(body) }),
  saveProvider: (body: unknown) => request<ProviderSettings>('/settings/provider', { method: 'PUT', body: JSON.stringify(body) }),
  provider: () => request<ProviderSettings>('/settings/provider'),
  providers: () => request<{ providers: ProviderPreset[] }>('/providers'),
  testProvider: (body: unknown) => request<{ ok: boolean; message: string; models: string[]; suggested_model?: string | null }>('/settings/provider/test', { method: 'POST', body: JSON.stringify(body) }),
  modelsStatus: () => request<Record<string, unknown>>('/models/status'),
  compare: (left_id: string, right_id: string) => request<{ changes: Record<string, unknown>[]; unchanged_claims: number; left: { title: string }; right: { title: string } }>('/compare', { method: 'POST', body: JSON.stringify({ left_id, right_id }) }),
  rerun: (id: string, confirmExternalProcessing = false) => request<AnalysisSummary>(`/analyses/${id}/rerun?confirm_external_processing=${confirmExternalProcessing}`, { method: 'POST' }),
  cancel: (id: string) => request<AnalysisSummary>(`/analyses/${id}/cancel`, { method: 'POST' }),
  delete: (id: string) => request<void>(`/analyses/${id}`, { method: 'DELETE' }),
  exportUrl: (id: string, format: string) => `${API}/analyses/${id}/export?format=${format}`,
};

export async function downloadExport(id: string, format: string, title: string) {
  const token = sessionStorage.getItem('verity_token');
  const response = await fetch(api.exportUrl(id, format), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) throw new Error('Could not download this report.');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'verity-report'}.${format === 'markdown' ? 'md' : format}`;
  document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
}
