import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../api/client', () => ({
  getEarlyWarnings: vi.fn(),
  ApiError: class MockApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
    }
  },
}));

import { getEarlyWarnings, ApiError } from '../api/client';
import type { EarlyWarningItem, EarlyWarningListResponse } from '../api/types';
import { EarlyWarningsPage } from '../pages/EarlyWarningsPage';

const mockGetEarlyWarnings = vi.mocked(getEarlyWarnings);

const baseItems: EarlyWarningItem[] = [
  {
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
    warning_type: 'TIME_WARNING|MEDIUM_RISK_WARNING',
    warning_priority: 'HIGH',
    warning_priority_label: 'Priority monitoring',
    warning_message: 'Project has elevated time-overrun risk.',
    risk_indicators: 'Time probability > 0.65 threshold',
    recommended_action: 'Review schedule and resource allocation.',
  },
  {
    project_code: 612183,
    project_name: 'Null Time Prob Project',
    state: 'MH',
    agency: 'Test Agency',
    report_month: 'April 2026',
    cost_overrun_probability: 0.1109,
    time_overrun_probability: null,
    combined_risk_score: 0.1109,
    risk_category: 'Low',
    score_status: 'partial',
    missing_component: 'time_overrun_probability',
    warning_type: 'DATA_COMPLETENESS_WARNING',
    warning_priority: 'LOW',
    warning_priority_label: 'Low priority',
    warning_message: 'Time probability missing.',
    risk_indicators: 'Missing time probability',
    recommended_action: 'Collect time data.',
  },
];

const baseResponse: EarlyWarningListResponse = {
  items: baseItems,
  page: 1,
  page_size: 20,
  total: 2,
  risk_category: null,
  warning_type: null,
};

// Multi-page response: 2 items but total=25 → 2 pages
const multiPageResponse: EarlyWarningListResponse = {
  ...baseResponse,
  total: 25,
};

describe('EarlyWarningsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows a loading state while fetching warnings', () => {
    mockGetEarlyWarnings.mockReturnValue(new Promise(() => {}));
    render(
      <MemoryRouter initialEntries={['/early-warnings']}>
        <Routes>
          <Route path="/early-warnings" element={<EarlyWarningsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'Loading early warnings…',
    );
  });

  it('renders warning rows from the real API response shape', async () => {
    mockGetEarlyWarnings.mockResolvedValue(baseResponse);
    render(
      <MemoryRouter initialEntries={['/early-warnings']}>
        <Routes>
          <Route path="/early-warnings" element={<EarlyWarningsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText('Kadapa Airport Terminal')).toBeInTheDocument(),
    );
    expect(screen.getByText('612786')).toBeInTheDocument();
    expect(screen.getByText('Airport Authority of India [AAI]')).toBeInTheDocument();
    expect(screen.getByText('Andhra Pradesh')).toBeInTheDocument();
    expect(screen.getAllByText('Medium').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('HIGH').length).toBeGreaterThanOrEqual(1);
    expect(mockGetEarlyWarnings).toHaveBeenCalledWith({
      risk_category: undefined,
      warning_type: undefined,
      page: 1,
      page_size: 20,
    });
  });

  it('applies the risk_category filter via the backend contract', async () => {
    mockGetEarlyWarnings.mockResolvedValue(baseResponse);
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/early-warnings']}>
        <Routes>
          <Route path="/early-warnings" element={<EarlyWarningsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText('Kadapa Airport Terminal')).toBeInTheDocument(),
    );
    const riskSelect = screen.getByLabelText('Risk category');
    await user.selectOptions(riskSelect, 'Medium');
    await waitFor(() =>
      expect(mockGetEarlyWarnings).toHaveBeenLastCalledWith({
        risk_category: 'Medium',
        warning_type: undefined,
        page: 1,
        page_size: 20,
      }),
    );
  });

  it('applies the warning_type filter via the backend contract', async () => {
    mockGetEarlyWarnings.mockResolvedValue(baseResponse);
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/early-warnings']}>
        <Routes>
          <Route path="/early-warnings" element={<EarlyWarningsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText('Kadapa Airport Terminal')).toBeInTheDocument(),
    );
    const typeSelect = screen.getByLabelText('Warning type');
    await user.selectOptions(typeSelect, 'TIME_WARNING|MEDIUM_RISK_WARNING');
    await waitFor(() =>
      expect(mockGetEarlyWarnings).toHaveBeenLastCalledWith({
        risk_category: undefined,
        warning_type: 'TIME_WARNING|MEDIUM_RISK_WARNING',
        page: 1,
        page_size: 20,
      }),
    );
  });

  it('paginates using the backend contract', async () => {
    mockGetEarlyWarnings.mockResolvedValue(multiPageResponse);
    render(
      <MemoryRouter initialEntries={['/early-warnings?page=1&page_size=20']}>
        <Routes>
          <Route path="/early-warnings" element={<EarlyWarningsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText('Page 1 of 2'));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() =>
      expect(mockGetEarlyWarnings).toHaveBeenLastCalledWith({
        risk_category: undefined,
        warning_type: undefined,
        page: 2,
        page_size: 20,
      }),
    );
  });

  it('disables prev on first page and next on last page', async () => {
    mockGetEarlyWarnings.mockResolvedValue(baseResponse);
    render(
      <MemoryRouter initialEntries={['/early-warnings?page=1&page_size=20']}>
        <Routes>
          <Route path="/early-warnings" element={<EarlyWarningsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText('Page 1 of 1'));
    expect(screen.getByRole('button', { name: 'Prev' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('shows an empty state when no items match the filters', async () => {
    mockGetEarlyWarnings.mockResolvedValue({
      ...baseResponse,
      items: [],
      total: 0,
    });
    render(
      <MemoryRouter initialEntries={['/early-warnings?risk_category=Unknown']}>
        <Routes>
          <Route path="/early-warnings" element={<EarlyWarningsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(
        screen.getByText('No early warnings match the selected filters.'),
      ).toBeInTheDocument(),
    );
  });

  it('shows a retryable error state when the API fails', async () => {
    mockGetEarlyWarnings.mockRejectedValue(
      new ApiError(0, 'Backend is unreachable.'),
    );
    render(
      <MemoryRouter initialEntries={['/early-warnings']}>
        <Routes>
          <Route path="/early-warnings" element={<EarlyWarningsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Backend is unreachable.');
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('links each warning row to the project detail route', async () => {
    mockGetEarlyWarnings.mockResolvedValue(baseResponse);
    render(
      <MemoryRouter initialEntries={['/early-warnings']}>
        <Routes>
          <Route path="/early-warnings" element={<EarlyWarningsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText('Kadapa Airport Terminal')).toBeInTheDocument(),
    );
    const row = screen.getByRole('button', {
      name: /View project 612786 - Kadapa Airport Terminal warning details/,
    });
    expect(row).toBeInTheDocument();
    fireEvent.click(row);
  });
});
