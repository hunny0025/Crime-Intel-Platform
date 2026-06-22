import { create } from 'zustand';

export interface SelectedEntity {
  id: string;
  type: 'person' | 'device' | 'location' | 'evidence' | 'event' | 'theory' | 'legal' | 'custom';
  name?: string;
  metadata?: Record<string, any>;
}

interface SelectionStore {
  selectedEntity: SelectedEntity | null;
  selectionHistory: SelectedEntity[];
  select: (entity: SelectedEntity | null) => void;
  goBack: () => void;
  clearSelection: () => void;
}

export const useSelectionStore = create<SelectionStore>((set) => ({
  selectedEntity: null,
  selectionHistory: [],
  select: (entity) =>
    set((state) => {
      if (!entity) {
        return { selectedEntity: null };
      }
      // Avoid duplicates in history consecutive list
      const last = state.selectionHistory[state.selectionHistory.length - 1];
      const history = last?.id === entity.id && last?.type === entity.type
        ? state.selectionHistory
        : [...state.selectionHistory, entity];
      return {
        selectedEntity: entity,
        selectionHistory: history,
      };
    }),
  goBack: () =>
    set((state) => {
      if (state.selectionHistory.length <= 1) {
        return { selectedEntity: null, selectionHistory: [] };
      }
      const newHistory = state.selectionHistory.slice(0, -1);
      const prevEntity = newHistory[newHistory.length - 1];
      return {
        selectedEntity: prevEntity,
        selectionHistory: newHistory,
      };
    }),
  clearSelection: () => set({ selectedEntity: null, selectionHistory: [] }),
}));
