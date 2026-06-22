import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type WorkspaceId =
  | 'mission-control'
  | 'case-setup'
  | 'evidence-lab'
  | 'graph-explorer'
  | 'timeline'
  | 'theory-engine'
  | 'legal-console'
  | 'court-prep'
  | 'copilot';

interface WorkspaceStore {
  activeWorkspace: WorkspaceId;
  panelSizes: Record<WorkspaceId, number[]>;
  aiSidebarOpen: boolean;
  bottomPanelOpen: boolean;
  rightInspectorOpen: boolean;
  setWorkspace: (id: WorkspaceId) => void;
  setPanelSizes: (workspace: WorkspaceId, sizes: number[]) => void;
  setAiSidebarOpen: (open: boolean) => void;
  setBottomPanelOpen: (open: boolean) => void;
  setRightInspectorOpen: (open: boolean) => void;
  toggleAiSidebar: () => void;
  toggleBottomPanel: () => void;
  toggleRightInspector: () => void;
}

const defaultPanelSizes: Record<WorkspaceId, number[]> = {
  'mission-control': [70, 30],
  'case-setup': [50, 50],
  'evidence-lab': [30, 70],
  'graph-explorer': [70, 30],
  'timeline': [65, 35],
  'theory-engine': [50, 50],
  'legal-console': [50, 50],
  'court-prep': [50, 50],
  'copilot': [100],
};

export const useWorkspaceStore = create<WorkspaceStore>()(
  persist(
    (set) => ({
      activeWorkspace: 'mission-control',
      panelSizes: defaultPanelSizes,
      aiSidebarOpen: true,
      bottomPanelOpen: true,
      rightInspectorOpen: true,
      setWorkspace: (id) => set({ activeWorkspace: id }),
      setPanelSizes: (workspace, sizes) =>
        set((state) => ({
          panelSizes: {
            ...state.panelSizes,
            [workspace]: sizes,
          },
        })),
      setAiSidebarOpen: (open) => set({ aiSidebarOpen: open }),
      setBottomPanelOpen: (open) => set({ bottomPanelOpen: open }),
      setRightInspectorOpen: (open) => set({ rightInspectorOpen: open }),
      toggleAiSidebar: () => set((state) => ({ aiSidebarOpen: !state.aiSidebarOpen })),
      toggleBottomPanel: () => set((state) => ({ bottomPanelOpen: !state.bottomPanelOpen })),
      toggleRightInspector: () => set((state) => ({ rightInspectorOpen: !state.rightInspectorOpen })),
    }),
    {
      name: 'crime-intel-workspace-store',
    }
  )
);
