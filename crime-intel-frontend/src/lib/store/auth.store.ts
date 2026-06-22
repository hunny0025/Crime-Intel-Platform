import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  user: string | null;
  agency: string | null;
  role: string | null;
  isAuthenticated: boolean;
  login: (user: string, agency: string, role: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: 'investigator_alpha', // Default to bypass login for demonstration
      agency: 'CBI',
      role: 'Lead Investigator',
      isAuthenticated: true,
      login: (user, agency, role) => set({ user, agency, role, isAuthenticated: true }),
      logout: () => set({ user: null, agency: null, role: null, isAuthenticated: false }),
    }),
    {
      name: 'crime-intel-auth-store',
    }
  )
);
