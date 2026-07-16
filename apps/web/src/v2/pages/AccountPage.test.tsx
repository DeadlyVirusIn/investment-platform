import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../state/SessionContext', () => ({
  useSession: () => ({ user: null, authenticated: false, loading: false, refresh: vi.fn(), signOut: vi.fn() }),
}));
vi.mock('../../lib/profile', () => ({ getProfile: vi.fn() }));
vi.mock('../../lib/auth', () => ({ login: vi.fn(), signup: vi.fn() }));
vi.mock('../../lib/feedback', () => ({ sendSignal: vi.fn() }));
vi.mock('../chrome/ArthosChrome', () => ({ ArthosPage: ({ children }: { children: React.ReactNode }) => <main>{children}</main> }));

import { AccountPage } from './AccountPage';

describe('AccountPage', () => {
  it('opens account creation for mode=signup', () => {
    render(<MemoryRouter initialEntries={['/account?mode=signup']}><AccountPage /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: /create your account/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/name \(optional\)/i)).toBeInTheDocument();
  });
});
