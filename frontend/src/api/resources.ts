/** Typed API functions, one group per resource. */

import { api, downloadFile } from './client';
import type {
  AnalysisResult,
  Artifact,
  AuthenticatedResponse,
  Catalogue,
  DashboardStats,
  HealthStatus,
  Paged,
  Project,
  ProviderDashboard,
  Run,
  RunEvent,
  TechStack,
  TokenPair,
  User,
  WorkspaceFile,
} from '@/types';

export const authApi = {
  register: (email: string, fullName: string, password: string) =>
    api.post<AuthenticatedResponse>('/auth/register', {
      email,
      full_name: fullName,
      password,
    }),

  login: (email: string, password: string) =>
    api.post<AuthenticatedResponse>('/auth/login', { email, password }),

  refresh: (refreshToken: string) =>
    api.post<TokenPair>('/auth/refresh', { refresh_token: refreshToken }),

  me: (signal?: AbortSignal) => api.get<User>('/auth/me', signal),

  updateProfile: (payload: { full_name?: string; theme_preference?: string }) =>
    api.patch<User>('/auth/me', payload),
};

export const projectApi = {
  list: (params: { search?: string; limit?: number; offset?: number } = {}, signal?: AbortSignal) => {
    const query = new URLSearchParams();
    if (params.search) query.set('search', params.search);
    query.set('limit', String(params.limit ?? 25));
    query.set('offset', String(params.offset ?? 0));
    return api.get<Paged<Project>>(`/projects?${query.toString()}`, signal);
  },

  create: (idea: string, name?: string, tags: string[] = []) =>
    api.post<Project>('/projects', { idea, name: name || undefined, tags }),

  get: (id: string, signal?: AbortSignal) => api.get<Project>(`/projects/${id}`, signal),

  update: (id: string, payload: { name?: string; tags?: string[] }) =>
    api.patch<Project>(`/projects/${id}`, payload),

  remove: (id: string) => api.delete<{ message: string }>(`/projects/${id}`),

  stats: (signal?: AbortSignal) => api.get<DashboardStats>('/projects/stats', signal),

  runs: (id: string, signal?: AbortSignal) => api.get<Run[]>(`/projects/${id}/runs`, signal),

  analyse: (id: string, signal?: AbortSignal) =>
    api.post<AnalysisResult>(`/projects/${id}/analyze`, undefined, signal),

  startRun: (id: string, stack?: Partial<TechStack>) =>
    api.post<Run>(`/projects/${id}/runs`, stack ? { tech_stack: stack } : {}),
};

export const runApi = {
  list: (limit = 20, signal?: AbortSignal) => api.get<Run[]>(`/runs?limit=${limit}`, signal),

  get: (id: string, signal?: AbortSignal) => api.get<Run>(`/runs/${id}`, signal),

  events: (id: string, after = 0, signal?: AbortSignal) =>
    api.get<RunEvent[]>(`/runs/${id}/events?after=${after}&limit=1000`, signal),

  files: (id: string, signal?: AbortSignal) =>
    api.get<WorkspaceFile[]>(`/runs/${id}/files`, signal),

  artifacts: (id: string, signal?: AbortSignal) =>
    api.get<Artifact[]>(`/runs/${id}/artifacts`, signal),

  cancel: (id: string) => api.post<{ message: string }>(`/runs/${id}/cancel`),

  download: (id: string, slug: string) =>
    downloadFile(`/runs/${id}/download`, `${slug || 'project'}.zip`),
};

export const artifactApi = {
  get: (id: string, signal?: AbortSignal) => api.get<Artifact>(`/artifacts/${id}`, signal),
};

export const catalogApi = {
  get: (signal?: AbortSignal) => api.get<Catalogue>('/catalog', signal),
};

export const systemApi = {
  health: (signal?: AbortSignal) => api.get<HealthStatus>('/health', signal),
};

export const providerApi = {
  dashboard: (signal?: AbortSignal) => api.get<ProviderDashboard>('/providers', signal),

  routing: (signal?: AbortSignal) =>
    api.get<Record<string, string>>('/providers/routing', signal),

  reset: (key: string) =>
    api.post<{ key: string; cleared: boolean; message: string }>(`/providers/${key}/reset`),
};
