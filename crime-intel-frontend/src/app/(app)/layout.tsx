'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useUIStore } from '@/lib/store/ui.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { useAuthStore } from '@/lib/store/auth.store';
import { ActivityRail } from '@/components/shell/activity-rail';
import { CommandBar } from '@/components/shell/command-bar';
import { StatusBar } from '@/components/shell/status-bar';
import { AISidebar } from '@/components/shell/ai-sidebar';
import { CommandPalette } from '@/components/shell/command-palette';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  
  // Zustand States
  const { searchOpen, setSearchOpen } = useUIStore();
  const { toggleAiSidebar, toggleBottomPanel } = useWorkspaceStore();
  const { isAuthenticated } = useAuthStore();

  // Redirect if not authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login');
    }
  }, [isAuthenticated, router]);

  // Global Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Toggle AI Sidebar (⌘B)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        toggleAiSidebar();
      }

      // Toggle Status Bar (⌘J)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        toggleBottomPanel();
      }

      // Workspace switching (⌘1 - ⌘9)
      if ((e.metaKey || e.ctrlKey) && e.key >= '1' && e.key <= '9') {
        const idx = parseInt(e.key) - 1;
        const workspacePaths = [
          '/',              // Mission Control
          '/cases',         // Case Setup
          '/evidence',      // Evidence Lab
          '/graph',         // Graph Explorer
          '/timeline',      // Timeline
          '/theory',        // Theory Engine
          '/legal/elements',// Legal Console
          '/legal/court',   // Court Prep
          '/copilot'        // Copilot
        ];
        if (workspacePaths[idx]) {
          e.preventDefault();
          router.push(workspacePaths[idx]);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleAiSidebar, toggleBottomPanel, router]);

  if (!isAuthenticated) {
    return null; // Don't flash layout if unauthenticated
  }

  return (
    <div className="flex h-screen w-screen bg-obsidian text-text-primary overflow-hidden font-sans">
      {/* 1. LEFT ACTIVITY RAIL */}
      <ActivityRail />

      {/* Main Workspace Column */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* 2. TOP COMMAND BAR */}
        <CommandBar onSearchOpen={() => setSearchOpen(true)} />

        {/* Center content split: active workspace page + AI Sidebar */}
        <div className="flex-1 flex min-h-0 relative overflow-hidden bg-base">
          <main className="flex-1 min-w-0 h-full overflow-hidden">
            {children}
          </main>

          {/* Persistent context-aware AI Sidebar */}
          <AISidebar />
        </div>

        {/* 3. STATUS BAR */}
        <StatusBar />
      </div>

      {/* 4. COMMAND PALETTE */}
      <CommandPalette open={searchOpen} setOpen={setSearchOpen} />
    </div>
  );
}
// Trigger dev watch reload
