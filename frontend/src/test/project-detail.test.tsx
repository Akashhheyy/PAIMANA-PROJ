import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  getProject: vi.fn(),
  getProjectRisk: vi.fn(),
  ApiError: class MockApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
    }
  },
}));

import { getProject, getProjectRisk, ApiError } from '../api/client';
import type { ProjectDetail, ProjectRiskResponse } from '../api/types';
import { ProjectDetailPage } from '../pages/ProjectDetailPage';

const mockGetProject = vi.mocked(getProject);
const mockGetProjectRisk = vi.mocked(getProjectRisk);

const baseProject: ProjectDetail = {
  project_code: 612786,
  project_name: 'Kadapa Airport Terminal',
  state: 'Andhra Pradesh',
  agency: 'Airport Authority of India [AAI]',
  report_month: 'April 2026',
  risk_category: 'Medium',
  approval_date: '2022-01-15',
  start_date: '2022-06-01',
  target_doc: '2024-12-31',
  revised_doc: '2025-06-30',
  original_cost_crore: 265.91,
  revised_cost_crore: 280.5,
  cumulative_expenditure_crore: 172.3,
  physical_progress_pct: 65.0,
  planned_horizon_months: 48.0,
};

const baseRisk: ProjectRiskResponse = {
  project_code: 612786,
  project_name: 'Kadapa Airport Terminal',
  state: 'Andhra Pradesh',
  agency: 'Airport Authority of India [AAI]',
  report_month: 'April 2026',
  cost_overrun_probability: 0.0403,
  time_overrun_probability: 0.9999,
  combined_risk_score: 0.5201,
  risk_category: 'Medium',
  score_status: 'complete',
  missing_component: 'none',
  warning_type: 'COST_AND_TIME_WARNING',
  warning_priority: 'P2',
  warning_priority_label: 'Medium',
  warning_message: 'Project has elevated time-overrun risk.',
  risk_indicators: 'Time probability > 0.65 threshold',
  recommended_action: 'Review schedule and resource allocation.',
};

describe('ProjectDetailPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows a loading state while fetching', () => {
    mockGetProject.mockReturnValue(new Promise(() => {}));
    mockGetProjectRisk.mockReturnValue(new Promise(() => {}));
    render(
      <MemoryRouter initialEntries={['/projects/612786']}>
        <Routes>
          <Route
            path="/projects/:projectCode"
            element={<ProjectDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'Loading project details…',
    );
  });

  it('renders project info and risk cards from real API data', async () => {
    mockGetProject.mockResolvedValue(baseProject);
    mockGetProjectRisk.mockResolvedValue(baseRisk);
    render(
      <MemoryRouter initialEntries={['/projects/612786']}>
        <Routes>
          <Route
            path="/projects/:projectCode"
            element={<ProjectDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText('Kadapa Airport Terminal')).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(
        screen.getByText(
          'Project 612786 - Airport Authority of India [AAI], Andhra Pradesh',
        ),
      ).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByText('Airport Authority of India [AAI]')).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByText('Andhra Pradesh')).toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getByText('65%')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Medium')).toBeInTheDocument());
  });

  it('shows “—” for null time probability instead of zero', async () => {
    mockGetProject.mockResolvedValue(baseProject);
    mockGetProjectRisk.mockResolvedValue({
      ...baseRisk,
      time_overrun_probability: null,
    });
    render(
      <MemoryRouter initialEntries={['/projects/612786']}>
        <Routes>
          <Route
            path="/projects/:projectCode"
            element={<ProjectDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText('—')).toBeInTheDocument(),
    );
  });

  it('renders warning details from the API', async () => {
    mockGetProject.mockResolvedValue(baseProject);
    mockGetProjectRisk.mockResolvedValue(baseRisk);
    render(
      <MemoryRouter initialEntries={['/projects/612786']}>
        <Routes>
          <Route
            path="/projects/:projectCode"
            element={<ProjectDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText('Warning type:')).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(
        screen.getAllByText('COST_AND_TIME_WARNING').length,
      ).toBeGreaterThanOrEqual(1),
    );
    await waitFor(() =>
      expect(screen.getByText('Recommended action:')).toBeInTheDocument(),
    );
  });

  it('shows a retryable error state when the API fails', async () => {
    mockGetProject.mockRejectedValue(new ApiError(404, 'Project not found'));
    mockGetProjectRisk.mockRejectedValue(new ApiError(404, 'Project not found'));
    render(
      <MemoryRouter initialEntries={['/projects/99999999']}>
        <Routes>
          <Route
            path="/projects/:projectCode"
            element={<ProjectDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        /not found in the current snapshot/,
      ),
    );
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('renders the Back to projects button', async () => {
    mockGetProject.mockResolvedValue(baseProject);
    mockGetProjectRisk.mockResolvedValue(baseRisk);
    render(
      <MemoryRouter initialEntries={['/projects/612786']}>
        <Routes>
          <Route
            path="/projects/:projectCode"
            element={<ProjectDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Back to projects' })).toBeInTheDocument(),
    );
  });
});
