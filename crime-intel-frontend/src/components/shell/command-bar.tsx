'use client';

import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FolderOpen, ChevronDown, Search, Bell, Activity } from 'lucide-react';
import { useCaseStore } from '@/lib/store/case.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { useUIStore } from '@/lib/store/ui.store';
import { casesApi } from '@/lib/api/client';
import { cn } from '@/lib/utils';

interface CommandBarProps {
  onSearchOpen: () => void;
}

export function CommandBar({ onSearchOpen }: CommandBarProps) {
  const { activeCaseId, activeCase, setActiveCase } = useCaseStore();
  const { activeWorkspace } = useWorkspaceStore();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Fetch cases list
  const { data: casesList = [] } = useQuery({
    queryKey: ['cases-list'],
    queryFn: casesApi.list,
  });

  // Set first case as active if none is active
  useEffect(() => {
    if (casesList.length > 0 && !activeCaseId) {
      setActiveCase(casesList[0]);
    }
  }, [casesList, activeCaseId, setActiveCase]);

  // Map workspace ID to friendly name
  const workspaceNames: Record<string, string> = {
    'mission-control': 'Mission Control',
    'case-setup': 'Case Setup',
    'evidence-lab': 'Evidence Lab',
    'graph-explorer': 'Graph Explorer',
    'timeline': 'Timeline Analysis',
    'theory-engine': 'Theory Engine',
    'legal-console': 'Legal Console',
    'court-prep': 'Court Prep',
    'copilot': 'Investigation Copilot',
  };

  return (
    <header className="h-10 bg-obsidian border-b border-border px-4 flex items-center justify-between shrink-0 select-none z-20">
      {/* Left: Case Selector & Breadcrumb */}
      <div className="flex items-center gap-3">
        {/* Case Switcher */}
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-1.5 px-2.5 py-0.5 rounded border border-border bg-surface text-[10px] font-mono font-bold text-intel-blue hover:border-intel-blue/50 focus:outline-none cursor-pointer"
          >
            <FolderOpen className="w-3 h-3 text-intel-blue" />
            <span className="truncate max-w-[130px]">
              {activeCase ? `CASE: ${activeCase.case_id.slice(0, 8)}...` : 'SELECT CASE'}
            </span>
            <ChevronDown className="w-2.5 h-2.5 text-text-secondary" />
          </button>

          {dropdownOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setDropdownOpen(false)} />
              <div className="absolute left-0 mt-1 w-64 rounded border border-border bg-overlay p-1 shadow-2xl z-50 animate-in fade-in slide-in-from-top-1 font-mono text-[10px]">
                <p className="px-2 py-1 text-[8px] font-bold text-text-muted uppercase tracking-wider border-b border-border-subtle/50 mb-1 select-none">
                  Switch Active Investigation
                </p>
                <div className="max-h-52 overflow-y-auto space-y-0.5">
                  {casesList.length === 0 ? (
                    <p className="px-2 py-1.5 text-text-muted">No cases found.</p>
                  ) : (
                    casesList.map((c) => (
                      <button
                        key={c.case_id}
                        onClick={() => {
                          setActiveCase(c);
                          setDropdownOpen(false);
                        }}
                        className={cn(
                          'w-full text-left px-2 py-1.5 rounded transition-all flex flex-col gap-0.5',
                          c.case_id === activeCaseId
                            ? 'bg-intel-blue-dim/20 text-intel-blue border border-intel-blue/15'
                            : 'text-text-secondary hover:bg-surface hover:text-text-primary border border-transparent'
                        )}
                      >
                        <span className="font-bold truncate">{c.case_type}</span>
                        <span className="text-[8px] text-text-muted truncate">{c.case_id}</span>
                      </button>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        <span className="text-text-muted font-mono text-[10px]">/</span>

        {/* Breadcrumb */}
        <div className="flex items-center text-[10px] font-mono font-medium text-text-secondary">
          <span className="text-text-primary font-bold">
            {workspaceNames[activeWorkspace] || 'Workspace'}
          </span>
          {activeCase && (
            <>
              <span className="text-text-muted mx-1.5">&gt;</span>
              <span className="text-text-muted truncate max-w-[120px]">
                {activeCase.case_type}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Right: Quick Search + Activity + Bell */}
      <div className="flex items-center gap-3">
        {/* Command Search Indicator */}
        <button
          onClick={onSearchOpen}
          className="flex items-center gap-1.5 px-2 py-0.5 rounded border border-border bg-surface text-text-secondary hover:text-text-primary text-[10px] font-mono transition-colors"
          title="Search menu (Ctrl+K)"
        >
          <Search className="w-3 h-3 text-text-secondary" />
          <span>Search...</span>
          <kbd className="pointer-events-none inline-flex h-3 select-none items-center gap-0.5 rounded border border-border bg-elevated px-1 font-mono text-[8px] font-medium text-text-muted">
            ⌘K
          </kbd>
        </button>

        {/* Pipeline Telemetry Indicator */}
        <div className="flex items-center gap-1.5 bg-surface border border-border rounded px-2 py-0.5 select-none" title="Pipeline Status: Active">
          <Activity className="w-3 h-3 text-intel-green animate-pulse" />
          <span className="text-[9px] font-mono font-bold tracking-wider text-intel-green">SYS.OK</span>
        </div>

        {/* Notification Bell */}
        <button className="text-text-secondary hover:text-text-primary transition-colors focus:outline-none p-1">
          <Bell className="w-3.5 h-3.5" />
        </button>
      </div>
    </header>
  );
}
