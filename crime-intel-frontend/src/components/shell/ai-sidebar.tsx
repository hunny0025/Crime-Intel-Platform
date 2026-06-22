'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useCaseStore } from '@/lib/store/case.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { useSelectionStore } from '@/lib/store/selection.store';
import { copilotApi } from '@/lib/api/client';
import { Bot, Sparkles, Send, Loader2, ArrowRight, BookOpen, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  intent?: string;
  suggestedActions?: string[];
  entitiesReferenced?: string[];
}

export function AISidebar() {
  const { activeCaseId } = useCaseStore();
  const { activeWorkspace, aiSidebarOpen } = useWorkspaceStore();
  const { selectedEntity } = useSelectionStore();

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      text: 'I am your investigative co-analyst. How can I assist you with this case today?',
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Context updates to suggestions
  const contextSuggestions = useMemo(() => {
    switch (activeWorkspace) {
      case 'mission-control':
        return [
          'Summarize the active case intelligence.',
          'Show overall threat profile for this jurisdiction.',
        ];
      case 'case-setup':
        return [
          'What evidence ingestion tasks are pending?',
          'Verify hash integrity for files.',
        ];
      case 'evidence-lab':
        return [
          'Analyze metadata anomalies in uploaded files.',
          'Extract timeline markers from files.',
        ];
      case 'graph-explorer':
        if (selectedEntity) {
          return [
            `Find paths connecting to ${selectedEntity.name || selectedEntity.id}`,
            `Show timeline of interactions for ${selectedEntity.name || selectedEntity.id}`,
          ];
        }
        return [
          'Find anomalies/disconnected clusters in the graph.',
          'Who is the most central suspect in this network?',
        ];
      case 'timeline':
        return [
          'Find temporal conflicts in communication records.',
          'Summarize event clusters around key dates.',
        ];
      case 'theory-engine':
        return [
          'Which hypothesis is most supported by evidence?',
          'Generate alternative scenarios for the heist.',
        ];
      case 'legal-console':
        return [
          'Are there any BNS sections currently unmapped?',
          'Audit procedural compliance status.',
        ];
      case 'court-prep':
        return [
          'Draft prosecution report based on findings.',
          'Simulate defense cross-examination arguments.',
        ];
      default:
        return [
          'Search knowledge graph for key entities.',
          'Analyze contradictions in this case.',
        ];
    }
  }, [activeWorkspace, selectedEntity]);

  // Query Mutation for Copilot
  const queryMutation = useMutation({
    mutationFn: async (queryText: string) => {
      if (!activeCaseId) throw new Error('No active case selected');
      
      const context = {
        workspace: activeWorkspace,
        selectedEntity: selectedEntity ? {
          id: selectedEntity.id,
          type: selectedEntity.type,
          name: selectedEntity.name
        } : null
      };

      return copilotApi.query(activeCaseId, queryText, context);
    },
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          sender: 'assistant',
          text: data.response_md,
          intent: data.intent,
          suggestedActions: data.suggested_actions,
          entitiesReferenced: data.entities_referenced,
        },
      ]);
    },
    onError: (err: any) => {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          sender: 'assistant',
          text: `⚠️ Query failed: ${err.message || 'Server error'}`,
        },
      ]);
    },
  });

  const handleSend = (textToSend?: string) => {
    const queryText = textToSend || input;
    if (!queryText.trim() || queryMutation.isPending || !activeCaseId) return;

    setMessages((prev) => [
      ...prev,
      {
        id: Date.now().toString(),
        sender: 'user',
        text: queryText,
      },
    ]);

    if (!textToSend) {
      setInput('');
    }

    queryMutation.mutate(queryText);
  };

  if (!aiSidebarOpen) return null;

  return (
    <aside className="w-80 h-full bg-surface border-l border-border flex flex-col shrink-0 select-none z-20">
      {/* Header */}
      <div className="h-10 border-b border-border px-3.5 flex items-center gap-2 bg-obsidian shrink-0">
        <Bot className="w-4 h-4 text-intel-purple" />
        <span className="text-[11px] font-mono font-bold text-text-primary uppercase tracking-wider">
          AI Co-Analyst
        </span>
        <div className="h-1.5 w-1.5 rounded-full bg-intel-purple shadow-[0_0_6px_#a78bfa] ml-auto" />
      </div>

      {/* Selected Entity Context Banner */}
      {selectedEntity && (
        <div className="px-3 py-1.5 bg-intel-purple-dim/10 border-b border-intel-purple/20 text-[9px] font-mono flex items-center justify-between animate-in fade-in slide-in-from-top-1">
          <span className="text-text-secondary">Focus Entity:</span>
          <span className="text-intel-purple font-bold truncate max-w-[150px]">
            {selectedEntity.type.toUpperCase()}: {selectedEntity.name || selectedEntity.id}
          </span>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3 font-mono text-[10px] scrollbar-thin">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn(
              'flex flex-col gap-1 max-w-[90%] rounded p-2.5 border',
              msg.sender === 'user'
                ? 'bg-elevated border-border ml-auto text-text-primary'
                : 'bg-obsidian border-border-subtle text-text-secondary'
            )}
          >
            <div className="flex items-center gap-1.5 mb-1 text-[8px] font-bold text-text-muted">
              {msg.sender === 'user' ? 'INVESTIGATOR' : 'CO-ANALYST'}
              {msg.intent && (
                <span className="bg-intel-purple/10 text-intel-purple border border-intel-purple/20 px-1 py-0.2 rounded text-[7px]">
                  INTENT: {msg.intent.toUpperCase()}
                </span>
              )}
            </div>
            
            <div className="leading-relaxed whitespace-pre-wrap select-text selection:bg-intel-purple/20 select-all">
              {msg.text}
            </div>

            {/* Referenced Entities list */}
            {msg.entitiesReferenced && msg.entitiesReferenced.length > 0 && (
              <div className="mt-2 pt-2 border-t border-border-subtle/50 flex flex-wrap gap-1">
                <span className="text-[8px] text-text-muted mr-1">Refs:</span>
                {msg.entitiesReferenced.map((ent) => (
                  <span
                    key={ent}
                    className="bg-surface border border-border text-text-primary px-1 py-0.2 rounded text-[8px] hover:border-intel-blue cursor-pointer"
                  >
                    {ent}
                  </span>
                ))}
              </div>
            )}

            {/* Suggested action triggers */}
            {msg.suggestedActions && msg.suggestedActions.length > 0 && (
              <div className="mt-2 pt-2 border-t border-border-subtle/50 flex flex-col gap-1">
                {msg.suggestedActions.map((act) => (
                  <button
                    key={act}
                    onClick={() => handleSend(act)}
                    className="text-left text-[9px] text-intel-blue hover:underline flex items-center gap-1 focus:outline-none"
                  >
                    <ArrowRight className="w-2.5 h-2.5 text-intel-blue" />
                    <span>{act}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {queryMutation.isPending && (
          <div className="flex items-center gap-2 text-text-muted bg-obsidian border border-border-subtle rounded p-2.5 max-w-[80%]">
            <Loader2 className="w-3.5 h-3.5 text-intel-purple animate-spin" />
            <span>AI model classifying & resolving query...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested prompts list */}
      <div className="px-3.5 py-2 bg-obsidian border-t border-border-subtle/40 flex flex-col gap-1 shrink-0">
        <div className="flex items-center gap-1 text-[8px] font-bold text-text-muted uppercase select-none">
          <Sparkles className="w-2.5 h-2.5 text-intel-purple" />
          <span>Suggested Prompts ({workspaceNamesBrief[activeWorkspace]})</span>
        </div>
        <div className="flex flex-col gap-1 max-h-24 overflow-y-auto">
          {contextSuggestions.map((sug) => (
            <button
              key={sug}
              onClick={() => handleSend(sug)}
              disabled={queryMutation.isPending}
              className="text-left text-[9px] text-text-secondary hover:text-text-primary hover:bg-surface/50 p-1 rounded transition-colors truncate focus:outline-none disabled:opacity-50"
            >
              {sug}
            </button>
          ))}
        </div>
      </div>

      {/* Input Form */}
      <div className="p-3 bg-obsidian border-t border-border shrink-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-1.5"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={queryMutation.isPending || !activeCaseId}
            placeholder={activeCaseId ? 'Ask co-analyst...' : 'Select a case first'}
            className="flex-1 bg-surface border border-border text-[10px] font-mono rounded px-2.5 py-1.5 text-text-primary placeholder-text-muted focus:outline-none focus:border-intel-purple/50 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={queryMutation.isPending || !input.trim() || !activeCaseId}
            className="h-7 w-7 rounded bg-intel-purple-dim/30 border border-intel-purple/40 text-intel-purple hover:bg-intel-purple hover:text-obsidian flex items-center justify-center transition-all disabled:opacity-50 disabled:hover:bg-intel-purple-dim/30 disabled:hover:text-intel-purple focus:outline-none cursor-pointer"
          >
            <Send className="w-3 h-3" />
          </button>
        </form>
      </div>
    </aside>
  );
}

const workspaceNamesBrief: Record<string, string> = {
  'mission-control': 'Control',
  'case-setup': 'Setup',
  'evidence-lab': 'Evidence',
  'graph-explorer': 'Graph',
  'timeline': 'Timeline',
  'theory-engine': 'Theory',
  'legal-console': 'Legal',
  'court-prep': 'Court',
  'copilot': 'Copilot',
};
