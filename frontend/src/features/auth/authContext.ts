import { createContext } from 'react';
import type { CurrentUser, RegisterRequest, RegisterResponse } from '@/api/types';

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

export interface AuthContextValue {
  status: AuthStatus;
  user: CurrentUser | null;
  login: (email: string, password: string) => Promise<CurrentUser>;
  register: (payload: RegisterRequest) => Promise<RegisterResponse>;
  verifyEmail: (token: string) => Promise<CurrentUser>;
  resendVerification: (email: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
