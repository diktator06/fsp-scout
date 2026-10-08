import { fireEvent, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import type { CurrentUser } from '@/api/types';
import { AuthContext, type AuthContextValue } from '@/features/auth/authContext';
import { renderWithTheme } from '@/test/render';
import { PersonalDataPanel } from './PersonalDataPanel';

const USER = {
  id: '6c71b5f8-1786-46a8-97de-3aef376e0ec1',
  email: 'candidate@example.com',
  role: 'candidate',
  is_email_verified: true,
} as CurrentUser;

function renderPanel(deleteAccount: AuthContextValue['deleteAccount']) {
  const auth = {
    status: 'authenticated',
    user: USER,
    deleteAccount,
  } as unknown as AuthContextValue;
  const router = createMemoryRouter(
    [
      { path: '/c/account', element: <PersonalDataPanel /> },
      { path: '/', element: <p>Главная</p> },
    ],
    { initialEntries: ['/c/account'] },
  );
  renderWithTheme(
    <AuthContext.Provider value={auth}>
      <RouterProvider router={router} />
    </AuthContext.Provider>,
  );
}

describe('PersonalDataPanel', () => {
  it('удаляет аккаунт только после ввода своего email', async () => {
    const deleteAccount = vi.fn().mockResolvedValue(undefined);
    renderPanel(deleteAccount);
    fireEvent.click(screen.getByRole('button', { name: /Удалить аккаунт/ }));
    const confirm = await screen.findByRole('button', { name: 'Удалить навсегда' });
    expect(confirm).toHaveProperty('disabled', true);
    expect(screen.getByText(/все попытки теста/)).toBeTruthy();

    const input = screen.getByLabelText('Введите email аккаунта');
    fireEvent.change(input, { target: { value: 'other@example.com' } });
    expect(confirm).toHaveProperty('disabled', true);
    fireEvent.change(input, { target: { value: ' Candidate@Example.com ' } });
    expect(confirm).toHaveProperty('disabled', false);

    fireEvent.click(confirm);
    await waitFor(() => expect(deleteAccount).toHaveBeenCalledWith('Candidate@Example.com'));
    expect(await screen.findByText('Главная')).toBeTruthy();
  });
});
