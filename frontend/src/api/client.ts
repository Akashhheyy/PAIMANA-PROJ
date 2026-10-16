/**
 * Typed API client for the PAIMANA AI backend.
 * Base URL comes from VITE_API_BASE_URL (see .env.example).
 * HTTP errors are surfaced as ApiError with the backend's `detail` message;
 * nullable fields are returned exactly as the backend sends them.
 */
import type {
  EarlyWarningListResponse,
  HealthResponse,
  ProgressDistributionResponse,
  ProjectDetail,
  ProjectListResponse,
  ProjectRiskResponse,
  RiskSummaryResponse,
} from './types';

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(
    /\/$/,
    '',
  );

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

interface ErrorBody {
  detail?: unknown;
}

function extractDetail(body: ErrorBody | null): string {
  if (!body || body.detail === undefined || body.detail === null) {
    return 'Unexpected response from server';
  }
  if (typeof body.detail === 'string') {
    return body.detail;
  }
  // FastAPI validation errors: array of {msg, loc, type}
  if (Array.isArray(body.detail)) {
    return body.detail
      .map((item: { msg?: string }) => item?.msg ?? 'Validation error')
      .join('; ');
  }
  return 'Unexpected response from server';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: 'application/json' },
      ...init,
    });
  } catch {
    throw new ApiError(
      0,
      'Backend is unreachable. Start it with: uvicorn backend.app.main:app --reload --port 8000',
    );
  }

  if (!response.ok) {
    let body: ErrorBody | null = null;
    try {
      body = (await response.json()) as ErrorBody;
    } catch {
      body = null;
    }
    throw new ApiError(response.status, extractDetail(body));
  }
  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export function getRiskSummary(): Promise<RiskSummaryResponse> {
  return request<RiskSummaryResponse>('/api/risk/summary');
}

export function getProgressDistribution(
  params?: { agency?: string; state?: string },
): Promise<ProgressDistributionResponse> {
  const search = new URLSearchParams();
  if (params?.agency) search.set('agency', params.agency);
  if (params?.state) search.set('state', params.state);
  const qs = search.toString();
  return request<ProgressDistributionResponse>(
    `/api/dashboard/progress-distribution${qs ? `?${qs}` : ''}`,
  );
}

export function getProjects(params?: {
  page?: number;
  page_size?: number;
  search?: string;
}): Promise<ProjectListResponse> {
  const search = new URLSearchParams();
  if (params?.page) search.set('page', String(params.page));
  if (params?.page_size) search.set('page_size', String(params.page_size));
  if (params?.search) search.set('search', params.search);
  const qs = search.toString();
  return request<ProjectListResponse>(`/api/projects${qs ? `?${qs}` : ''}`);
}

export function getProject(project_code: string | number): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/api/projects/${String(project_code)}`);
}

export function getProjectRisk(
  project_code: string | number,
): Promise<ProjectRiskResponse> {
  return request<ProjectRiskResponse>(
    `/api/projects/${String(project_code)}/risk`,
  );
}

export function getEarlyWarnings(params?: {
  risk_category?: string;
  warning_type?: string;
  page?: number;
  page_size?: number;
}): Promise<EarlyWarningListResponse> {
  const search = new URLSearchParams();
  if (params?.risk_category) search.set('risk_category', params.risk_category);
  if (params?.warning_type) search.set('warning_type', params.warning_type);
  if (params?.page) search.set('page', String(params.page));
  if (params?.page_size) search.set('page_size', String(params.page_size));
  const qs = search.toString();
  return request<EarlyWarningListResponse>(
    `/api/early-warnings${qs ? `?${qs}` : ''}`,
  );
}
