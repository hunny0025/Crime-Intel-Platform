import { create } from 'zustand';

interface UIState {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  searchOpen: boolean;
  setSearchOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  activeTab: 'overview',
  setActiveTab: (tab) => set({ activeTab: tab }),
  searchOpen: false,
  setSearchOpen: (open) => set({ searchOpen: open }),
}));
