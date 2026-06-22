import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Case } from '../api/types';

interface CaseState {
  activeCaseId: string | null;
  activeCase: Case | null;
  setActiveCaseId: (id: string | null) => void;
  setActiveCase: (caseObj: Case | null) => void;
}

export const useCaseStore = create<CaseState>()(
  persist(
    (set) => ({
      activeCaseId: null,
      activeCase: null,
      setActiveCaseId: (id) => set({ activeCaseId: id }),
      setActiveCase: (caseObj) => set({ activeCase: caseObj, activeCaseId: caseObj ? caseObj.case_id : null }),
    }),
    {
      name: 'crime-intel-case-store',
    }
  )
);
