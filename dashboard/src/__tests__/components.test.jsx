import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ThreadCard from '../components/ThreadCard';
import ThreadList from '../components/ThreadList';
import SearchBar from '../components/SearchBar';
import Stats from '../components/Stats';
import CopyButton from '../components/CopyButton';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const MOCK_THREAD = {
  id: "test-123",
  source: "claude",
  source_url: "https://claude.ai/chat/test-123",
  title: "Auth System Design with JWT Tokens",
  conversation_type: "build",
  summary: "Discussed JWT-based authentication.",
  key_takeaways: ["Use JWT", "15-min access tokens"],
  open_threads: ["Token revocation strategy?"],
  tags: ["JWT", "auth", "security"],
  artifacts: [],
  extraction_status: "done",
  message_count: 4,
  created_at: new Date().toISOString(),
};

// --- ThreadCard ---

describe('ThreadCard', () => {
  it('renders thread title', () => {
    render(
      <MemoryRouter>
        <ThreadCard thread={MOCK_THREAD} />
      </MemoryRouter>
    );
    expect(screen.getByText('Auth System Design with JWT Tokens')).toBeInTheDocument();
  });

  it('renders summary', () => {
    render(
      <MemoryRouter>
        <ThreadCard thread={MOCK_THREAD} />
      </MemoryRouter>
    );
    expect(screen.getByText('Discussed JWT-based authentication.')).toBeInTheDocument();
  });

  it('renders key takeaways', () => {
    render(
      <MemoryRouter>
        <ThreadCard thread={MOCK_THREAD} />
      </MemoryRouter>
    );
    expect(screen.getByText('Use JWT')).toBeInTheDocument();
    expect(screen.getByText('15-min access tokens')).toBeInTheDocument();
  });

  it('renders tags', () => {
    render(
      <MemoryRouter>
        <ThreadCard thread={MOCK_THREAD} />
      </MemoryRouter>
    );
    expect(screen.getByText('JWT')).toBeInTheDocument();
    expect(screen.getByText('auth')).toBeInTheDocument();
    expect(screen.getByText('security')).toBeInTheDocument();
  });

  it('renders open thread', () => {
    render(
      <MemoryRouter>
        <ThreadCard thread={MOCK_THREAD} />
      </MemoryRouter>
    );
    expect(screen.getByText(/Token revocation strategy/)).toBeInTheDocument();
  });

  it('renders conversation type badge', () => {
    render(
      <MemoryRouter>
        <ThreadCard thread={MOCK_THREAD} />
      </MemoryRouter>
    );
    expect(screen.getByText('Build')).toBeInTheDocument();
  });

  it('renders failed extraction state', () => {
    const failed = {
      ...MOCK_THREAD,
      extraction_status: "failed",
      extraction_error: "API rate limited",
    };
    render(
      <MemoryRouter>
        <ThreadCard thread={failed} />
      </MemoryRouter>
    );
    expect(screen.getByText('Extraction Failed')).toBeInTheDocument();
    expect(screen.getByText('API rate limited')).toBeInTheDocument();
  });

  it('renders processing state', () => {
    const processing = { ...MOCK_THREAD, extraction_status: "processing" };
    render(
      <MemoryRouter>
        <ThreadCard thread={processing} />
      </MemoryRouter>
    );
    expect(screen.getByText('Extracting context...')).toBeInTheDocument();
  });

  it('has a View link to thread detail', () => {
    render(
      <MemoryRouter>
        <ThreadCard thread={MOCK_THREAD} />
      </MemoryRouter>
    );
    const viewLink = screen.getByText(/View/);
    expect(viewLink.closest('a')).toHaveAttribute('href', '/thread/test-123');
  });
});

// --- SearchBar ---

describe('SearchBar', () => {
  it('renders input with placeholder', () => {
    render(<SearchBar value="" onChange={() => {}} />);
    expect(screen.getByPlaceholderText('Search your contexts...')).toBeInTheDocument();
  });

  it('calls onChange when user types', () => {
    const onChange = vi.fn();
    render(<SearchBar value="" onChange={onChange} />);
    fireEvent.change(screen.getByPlaceholderText('Search your contexts...'), {
      target: { value: 'jwt' },
    });
    expect(onChange).toHaveBeenCalledWith('jwt');
  });
});

// --- Stats ---

describe('Stats', () => {
  it('returns null when stats is null', () => {
    const { container } = render(<Stats stats={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows toggle button', () => {
    render(<Stats stats={{ total_threads: 5, threads_this_week: 2, total_pulls: 3 }} />);
    expect(screen.getByText(/Stats/)).toBeInTheDocument();
  });

  it('shows stats when expanded', () => {
    render(<Stats stats={{ total_threads: 42, threads_this_week: 7, total_pulls: 18 }} />);
    fireEvent.click(screen.getByText(/Stats/));
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('18')).toBeInTheDocument();
  });
});

// --- CopyButton ---

describe('CopyButton', () => {
  it('renders with default label', () => {
    render(<CopyButton getText="test" />);
    expect(screen.getByRole('button', { name: 'Copy Context' })).toBeInTheDocument();
  });

  it('renders with custom label', () => {
    render(<CopyButton getText="test" label="Copy Code" />);
    expect(screen.getByRole('button', { name: 'Copy Code' })).toBeInTheDocument();
  });
});

// --- ThreadList ---

function mockFetch(threadsData, statsData) {
  return vi.spyOn(global, 'fetch').mockImplementation((url) => {
    if (url.includes('/api/stats')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(statsData || {
          total_threads: 0, total_pulls: 0, threads_this_week: 0, pulls_this_week: 0,
        }),
      });
    }
    if (url.includes('/api/threads')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(threadsData || { threads: [], total: 0 }),
      });
    }
    return Promise.reject(new Error('Unknown URL'));
  });
}

describe('ThreadList', () => {
  it('shows loading state initially', () => {
    vi.spyOn(global, 'fetch').mockImplementation(() => new Promise(() => {}));
    render(
      <MemoryRouter>
        <ThreadList />
      </MemoryRouter>
    );
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('shows error when backend is unreachable', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('Network error'));
    render(
      <MemoryRouter>
        <ThreadList />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText(/Can't connect to server/)).toBeInTheDocument();
    });
  });

  it('renders thread cards when data loads', async () => {
    mockFetch(
      { threads: [MOCK_THREAD], total: 1 },
      { total_threads: 1, total_pulls: 0, threads_this_week: 1, pulls_this_week: 0 }
    );
    render(
      <MemoryRouter>
        <ThreadList />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText('Auth System Design with JWT Tokens')).toBeInTheDocument();
    });
  });

  it('filters threads by search query', async () => {
    const thread2 = {
      ...MOCK_THREAD,
      id: "test-456",
      title: "Pricing Strategy Discussion",
      summary: "Explored pricing models.",
      key_takeaways: [],
      open_threads: [],
      tags: ["pricing"],
    };

    mockFetch(
      { threads: [MOCK_THREAD, thread2], total: 2 },
      { total_threads: 2, total_pulls: 0, threads_this_week: 2, pulls_this_week: 0 }
    );

    render(
      <MemoryRouter>
        <ThreadList />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Auth System Design with JWT Tokens')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText('Search your contexts...'), {
      target: { value: 'pricing' },
    });

    expect(screen.queryByText('Auth System Design with JWT Tokens')).not.toBeInTheDocument();
    expect(screen.getByText('Pricing Strategy Discussion')).toBeInTheDocument();
  });

  it('shows empty state when no threads', async () => {
    mockFetch({ threads: [], total: 0 });
    render(
      <MemoryRouter>
        <ThreadList />
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(screen.getByText(/No contexts yet/)).toBeInTheDocument();
    });
  });
});
