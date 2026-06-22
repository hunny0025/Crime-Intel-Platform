'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutDashboard, FolderOpen, Database, Network, Clock, 
  Brain, Scale, Hammer, Bot, Settings, User, LogOut
} from 'lucide-react';
import { useWorkspaceStore, WorkspaceId } from '@/lib/store/workspace.store';
import { useAuthStore } from '@/lib/store/auth.store';
import { cn } from '@/lib/utils';

interface WorkspaceItem {
  id: WorkspaceId;
  name: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  shortcut: string;
}

const workspaces: WorkspaceItem[] = [
  { id: 'mission-control', name: 'Mission Control', path: '/', icon: LayoutDashboard, shortcut: '⌘1' },
  { id: 'case-setup', name: 'Case Setup', path: '/cases', icon: FolderOpen, shortcut: '⌘2' },
  { id: 'evidence-lab', name: 'Evidence Lab', path: '/evidence', icon: Database, shortcut: '⌘3' },
  { id: 'graph-explorer', name: 'Graph Explorer', path: '/graph', icon: Network, shortcut: '⌘4' },
  { id: 'timeline', name: 'Timeline', path: '/timeline', icon: Clock, shortcut: '⌘5' },
  { id: 'theory-engine', name: 'Theory Engine', path: '/theory', icon: Brain, shortcut: '⌘6' },
  { id: 'legal-console', name: 'Legal Console', path: '/legal/elements', icon: Scale, shortcut: '⌘7' },
  { id: 'court-prep', name: 'Court Prep', path: '/legal/court', icon: Hammer, shortcut: '⌘8' },
  { id: 'copilot', name: 'Copilot', path: '/copilot', icon: Bot, shortcut: '⌘9' },
];

export function ActivityRail() {
  const pathname = usePathname();
  const { activeWorkspace, setWorkspace } = useWorkspaceStore();
  const { user, agency, role, logout } = useAuthStore();
  
  // Update workspace store when path change
  React.useEffect(() => {
    const active = workspaces.find(w => {
      if (w.path === '/') return pathname === '/';
      return pathname.startsWith(w.path);
    });
    if (active && active.id !== activeWorkspace) {
      setWorkspace(active.id);
    }
  }, [pathname, activeWorkspace, setWorkspace]);

  return (
    <aside className="w-12 h-screen bg-obsidian border-r border-border flex flex-col items-center py-3 justify-between shrink-0 select-none z-30">
      {/* Top: Logo / OS Icon */}
      <div className="flex flex-col items-center gap-4 w-full">
        <div className="h-8 w-8 rounded bg-intel-blue flex items-center justify-center font-bold text-obsidian text-[11px] shadow-[0_0_10px_rgba(74,158,255,0.3)]">
          IOS
        </div>
        
        <div className="w-8 h-[1px] bg-border-subtle" />

        {/* Workspaces List */}
        <nav className="flex flex-col gap-1 w-full items-center">
          {workspaces.map((ws) => {
            const Icon = ws.icon;
            const isActive = activeWorkspace === ws.id;

            return (
              <Link
                key={ws.id}
                href={ws.path}
                onClick={() => setWorkspace(ws.id)}
                className={cn(
                  "relative group flex items-center justify-center w-8 h-8 rounded transition-all duration-150 border border-transparent",
                  isActive
                    ? "bg-intel-blue-dim/20 text-intel-blue border-intel-blue/30 shadow-[0_0_8px_rgba(74,158,255,0.06)]"
                    : "text-text-secondary hover:text-text-primary hover:bg-surface/50"
                )}
              >
                {/* Active Indicator Bar */}
                {isActive && (
                  <div className="absolute left-0 top-1.5 bottom-1.5 w-[2px] bg-intel-blue rounded-r" />
                )}

                <Icon className="w-4 h-4 shrink-0" />

                {/* Tooltip */}
                <div className="absolute left-14 hidden group-hover:flex flex-col bg-overlay border border-border text-text-primary text-[10px] font-mono px-2 py-1 rounded shadow-xl whitespace-nowrap z-50 pointer-events-none">
                  <div className="font-bold">{ws.name}</div>
                  <div className="text-text-muted text-[8px]">Shortcut: {ws.shortcut}</div>
                </div>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Bottom: Settings, Profile, Logout */}
      <div className="flex flex-col items-center gap-2 w-full">
        <div className="w-8 h-[1px] bg-border-subtle" />

        {/* User Profile Info Trigger */}
        <div className="relative group flex items-center justify-center w-8 h-8 rounded text-text-secondary hover:text-text-primary hover:bg-surface/50 cursor-pointer">
          <User className="w-4 h-4 shrink-0" />
          <div className="absolute left-14 hidden group-hover:flex flex-col bg-overlay border border-border text-text-primary text-[10px] font-mono px-3 py-2 rounded shadow-xl whitespace-nowrap z-50 pointer-events-none">
            <div className="font-bold text-text-primary">{user || 'Investigator'}</div>
            <div className="text-text-secondary text-[9px]">{agency || 'Agency'}</div>
            <div className="text-text-muted text-[8px]">{role || 'Special Agent'}</div>
          </div>
        </div>

        {/* Logout */}
        <button
          onClick={logout}
          className="relative group flex items-center justify-center w-8 h-8 rounded text-text-secondary hover:text-intel-red hover:bg-intel-red-dim/10 transition-colors"
          title="Sign Out"
        >
          <LogOut className="w-4 h-4 shrink-0" />
          <div className="absolute left-14 hidden group-hover:flex bg-overlay border border-border text-intel-red text-[10px] font-mono px-2 py-1 rounded shadow-xl whitespace-nowrap z-50 pointer-events-none">
            Sign Out
          </div>
        </button>
      </div>
    </aside>
  );
}
