'use client';

import React, { useState, useEffect } from 'react';
import { Command } from 'cmdk';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { 
  Search, Terminal, FileText, Database, Network, Clock, 
  Brain, Scale, Hammer, Bot, LayoutDashboard, FolderOpen,
  Settings, X
} from 'lucide-react';
import { useWorkspaceStore, WorkspaceId } from '@/lib/store/workspace.store';
import { useCaseStore } from '@/lib/store/case.store';
import { casesApi } from '@/lib/api/client';
import { cn } from '@/lib/utils';

interface CommandPaletteProps {
  open: boolean;
  setOpen: (open: boolean) => void;
}

export function CommandPalette({ open, setOpen }: CommandPaletteProps) {
  const router = useRouter();
  const { setWorkspace, toggleAiSidebar, toggleBottomPanel } = useWorkspaceStore();
  const { activeCaseId, setActiveCase } = useCaseStore();
  const [search, setSearch] = useState('');

  // Fetch cases
  const { data: casesList = [] } = useQuery({
    queryKey: ['cases-list'],
    queryFn: casesApi.list,
    enabled: open,
  });

  // Toggle command palette on Cmd+K/Ctrl+K
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen(!open);
      }
    };
    document.addEventListener('keydown', down);
    return () => document.removeEventListener('keydown', down);
  }, [open, setOpen]);

  const runCommand = (action: () => void) => {
    action();
    setOpen(false);
    setSearch('');
  };

  const navigateTo = (path: string, workspaceId: WorkspaceId) => {
    runCommand(() => {
      setWorkspace(workspaceId);
      router.push(path);
    });
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-obsidian/85 backdrop-blur-sm z-50 animate-in fade-in duration-150"
        onClick={() => setOpen(false)}
      />

      {/* Palette dialog */}
      <div className="fixed top-[15%] left-1/2 -translate-x-1/2 w-full max-w-lg rounded border border-border bg-overlay shadow-2xl z-50 overflow-hidden font-mono text-[10px] animate-in fade-in slide-in-from-top-4 duration-200">
        <Command label="Global Command Menu" className="w-full flex flex-col" value={search} onValueChange={setSearch}>
          {/* Input Header */}
          <div className="flex items-center gap-2 border-b border-border-subtle px-3 py-2 bg-obsidian shrink-0">
            <Search className="w-3.5 h-3.5 text-text-secondary shrink-0" />
            <Command.Input 
              placeholder="Search workspaces, cases, or execute pipeline commands..."
              className="w-full bg-transparent text-text-primary placeholder-text-muted text-[10px] focus:outline-none border-none outline-none font-mono"
              autoFocus
            />
            <button 
              onClick={() => setOpen(false)} 
              className="text-text-secondary hover:text-text-primary p-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* List Area */}
          <Command.List className="max-h-64 overflow-y-auto p-1.5 space-y-1.5 scrollbar-thin">
            <Command.Empty className="px-2 py-3 text-text-muted text-center">
              No intelligence elements or actions match your query.
            </Command.Empty>

            {/* Group: Workspaces */}
            <Command.Group heading="WORKSPACES" className="text-text-muted text-[8px] font-bold tracking-wider select-none px-2 py-0.5">
              <Command.Item 
                onSelect={() => navigateTo('/', 'mission-control')}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <LayoutDashboard className="w-3 h-3 text-intel-blue" />
                <span>Mission Control</span>
              </Command.Item>
              <Command.Item 
                onSelect={() => navigateTo('/cases', 'case-setup')}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <FolderOpen className="w-3 h-3 text-intel-blue" />
                <span>Case Setup & Evidence Files</span>
              </Command.Item>
              <Command.Item 
                onSelect={() => navigateTo('/evidence', 'evidence-lab')}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <Database className="w-3 h-3 text-intel-blue" />
                <span>Evidence Lab Vault</span>
              </Command.Item>
              <Command.Item 
                onSelect={() => navigateTo('/graph', 'graph-explorer')}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <Network className="w-3 h-3 text-intel-blue" />
                <span>Knowledge Graph Explorer</span>
              </Command.Item>
              <Command.Item 
                onSelect={() => navigateTo('/timeline', 'timeline')}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <Clock className="w-3 h-3 text-intel-blue" />
                <span>Forensic Timeline</span>
              </Command.Item>
              <Command.Item 
                onSelect={() => navigateTo('/theory', 'theory-engine')}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <Brain className="w-3 h-3 text-intel-blue" />
                <span>ORACLE Theory Engine</span>
              </Command.Item>
              <Command.Item 
                onSelect={() => navigateTo('/legal/elements', 'legal-console')}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <Scale className="w-3 h-3 text-intel-blue" />
                <span>Legal Console (BNS Sections)</span>
              </Command.Item>
              <Command.Item 
                onSelect={() => navigateTo('/legal/court', 'court-prep')}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <Hammer className="w-3 h-3 text-intel-blue" />
                <span>Court Preparation Console</span>
              </Command.Item>
              <Command.Item 
                onSelect={() => navigateTo('/copilot', 'copilot')}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <Bot className="w-3 h-3 text-intel-blue" />
                <span>Copilot Chat Workspace</span>
              </Command.Item>
            </Command.Group>

            <div className="h-[1px] bg-border-subtle my-1.5" />

            {/* Group: Fast Actions */}
            <Command.Group heading="SYSTEM ACTIONS" className="text-text-muted text-[8px] font-bold tracking-wider select-none px-2 py-0.5">
              <Command.Item 
                onSelect={() => runCommand(toggleAiSidebar)}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <Terminal className="w-3 h-3 text-intel-purple" />
                <span>Toggle AI Co-Analyst Panel (⌘B)</span>
              </Command.Item>
              <Command.Item 
                onSelect={() => runCommand(toggleBottomPanel)}
                className="flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface text-text-secondary hover:text-text-primary cursor-pointer transition-colors"
              >
                <Terminal className="w-3 h-3 text-intel-amber" />
                <span>Toggle Bottom Status Bar Panel (⌘J)</span>
              </Command.Item>
            </Command.Group>

            {/* Group: Active Cases Switcher */}
            {casesList.length > 0 && (
              <>
                <div className="h-[1px] bg-border-subtle my-1.5" />
                <Command.Group heading="SWITCH CASE" className="text-text-muted text-[8px] font-bold tracking-wider select-none px-2 py-0.5">
                  {casesList.map((c) => (
                    <Command.Item 
                      key={c.case_id}
                      onSelect={() => runCommand(() => setActiveCase(c))}
                      className={cn(
                        "flex items-center gap-2.5 px-2 py-1.5 rounded hover:bg-surface cursor-pointer transition-colors",
                        c.case_id === activeCaseId ? "text-intel-blue font-bold" : "text-text-secondary hover:text-text-primary"
                      )}
                    >
                      <FolderOpen className="w-3 h-3 shrink-0" />
                      <span className="truncate">{c.case_type} ({c.case_id.slice(0, 8)})</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              </>
            )}
          </Command.List>

          {/* Footer Shortcuts Info */}
          <div className="border-t border-border-subtle px-3 py-2 bg-obsidian flex justify-between items-center text-[8px] text-text-muted select-none">
            <span>↑↓ to navigate, Enter to run</span>
            <span>ESC to cancel</span>
          </div>
        </Command>
      </div>
    </>
  );
}
