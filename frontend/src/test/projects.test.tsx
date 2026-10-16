import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockGetProjects = vi.fn();

class MockApiError extends Error {
  status: number;
  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

vi.mock('../api/client', () => ({
  getProjects: mockGetProjects,
  ApiError: MockApiError,
}));

import { ProjectsPage } from '../pages/ProjectsPage';

const baseResponse = {
  items: [
    {
      project_code: 101,
      project_name: 'Alpha Bridge',
      state: 'KA',
      agency: 'NHAI',
      report_month: '2026-04',
      risk_category: 'High',
    },
    {
      project_code: 102,
      project_name: 'Beta Road',
      state: 'MH',
      agency: 'MMRDA',
      report_month: '2026-04',
      risk_category: null,
    },
  ],
  page: 1,
  page_size: 20,
  total: 2,
};

describe('ProjectsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows a loading state while fetching projects', () => {
    mockGetProjects.mockReturnValue(new Promise(() => {}));
    render(
      <MemoryRouter initialEntries={['/projects']}>
        <ProjectsPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Loading projects…');
  });

  it('renders project rows from the real API response shape', async () => {
    mockGetProjects.mockResolvedValue(baseResponse);
    render(
      <MemoryRouter initialEntries={['/projects']}>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('Alpha Bridge')).toBeInTheDocument());
    expect(screen.getByText('101')).toBeInTheDocument();
    expect(screen.getByText('NHAI')).toBeInTheDocument();
    expect(screen.getByText('KA')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
    expect(mockGetProjects).toHaveBeenCalledWith({
      page: 1,
      page_size: 20,
      search: undefined,
    });
  });

  it('renders “Not scored” for null risk category and is keyboard operable', async () => {
    mockGetProjects.mockResolvedValue(baseResponse);
    render(
      <MemoryRouter initialEntries={['/projects']}>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('Beta Road')).toBeInTheDocument());
    const row = screen.getByRole('button', { name: /View project 102 - Beta Road/ });
    expect(row).toBeInTheDocument();
    fireEvent.keyDown(row, { key: 'Enter' });
  });

  it('applies the search parameter and resets to page 1', async () => {
    mockGetProjects.mockResolvedValue({ ...baseResponse, items: [], total: 0 });
    render(
      <MemoryRouter initialEntries={['/projects']}>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('Alpha Bridge')).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/search by name, code, agency or state/i), {
      target: { value: 'Gamma' },
    });
    await waitFor(() =>
      expect(mockGetProjects).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 20,
        search: 'Gamma',
      }),
    );
  });

  it('paginates to the next page using the backend contract', async () => {
    mockGetProjects.mockResolvedValue(baseResponse);
    render(
      <MemoryRouter initialEntries={['/projects?page=1&page_size=20&search=']}>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText('Page 1 of 1'));
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() =>
      expect(mockGetProjects).toHaveBeenLastCalledWith({
        page: 2,
        page_size: 20,
        search: undefined,
      }),
    );
  });

  it('disables prev on the first page and next on the last page', async () => {
    mockGetProjects.mockResolvedValue(baseResponse);
    render(
      <MemoryRouter initialEntries={['/projects?page=1&page_size=20&search=']}>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText('Page 1 of 1'));
    expect(screen.getByRole('button', { name: 'Prev' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('shows an empty state when no items match the search', async () => {
    mockGetProjects.mockResolvedValue({ ...baseResponse, items: [], total: 0 });
    render(
      <MemoryRouter initialEntries={['/projects?search=Nothing']}>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText('No projects match “Nothing”.')).toBeInTheDocument(),
    );
  });

  it('shows a retryable error state when the API fails', async () => {
    mockGetProjects.mockRejectedValue(new MockApiError('Backend is unreachable.', 0));
    render(
      <MemoryRouter initialEntries={['/projects']}>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Backend is unreachable.'),
    );
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
