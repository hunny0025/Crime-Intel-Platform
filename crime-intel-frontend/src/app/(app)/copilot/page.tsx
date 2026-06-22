'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  MessageSquare, Send, Sparkles, Zap, Bot, User,
  Clock, ChevronRight, Search, Shield, Brain, Target,
  AlertTriangle, FileText, BarChart3, Scale, Loader2
} from 'lucide-react';
import { copilotApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  intent?: string;
  confidence?: number;
  actions?: string[];
  queryTimeMs?: number;
  timestamp: Date;
}

const SUGGESTION_CHIPS = [
  { label: 'Summarize the case', icon: FileText },
  { label: 'Show contradictions', icon: AlertTriangle },
  { label: 'What evidence is missing?', icon: Search },
  { label: 'Is this case court ready?', icon: Scale },
  { label: 'Show case timeline', icon: Clock },
  { label: 'List all evidence', icon: BarChart3 },
  { label: 'Show theories ranked', icon: Brain },
  { label: 'Explain reasoning', icon: Sparkles },
];

const INTENT_COLORS: Record<string, string> = {
  entity_connections: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
  contradictions: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
  evidence_gaps: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  hypothesis_support: 'text-violet-400 bg-violet-500/10 border-violet-500/30',
  legal_readiness: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  timeline: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  evidence_list: 'text-orange-400 bg-orange-500/10 border-orange-500/30',
  case_summary: 'text-teal-400 bg-teal-500/10 border-teal-500/30',
  reasoning_explanation: 'text-pink-400 bg-pink-500/10 border-pink-500/30',
};

export default function CopilotPage() {
  const { activeCaseId } = useCaseStore();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const queryMutation = useMutation({
    mutationFn: async (query: string) => {
      if (!activeCaseId) throw new Error('No active case selected');
      return copilotApi.query(activeCaseId, query);
    },
    onSuccess: (data) => {
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: data.response_md,
        intent: data.intent,
        confidence: data.confidence,
        actions: data.suggested_actions,
        queryTimeMs: data.query_time_ms,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMsg]);
    },
    onError: (err: any) => {
      const errorMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `## ❌ Error\n\n${err?.response?.data?.detail || err.message || 'Failed to process query. Please try again.'}`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMsg]);
    },
  });

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || queryMutation.isPending) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    queryMutation.mutate(trimmed);
  }, [input, queryMutation]);

  const handleChipClick = useCallback((label: string) => {
    setInput(label);
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: label,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    queryMutation.mutate(label);
  }, [queryMutation]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Simple markdown-to-HTML (tables, headers, bold, bullets, blockquotes, code)
  const renderMarkdown = (md: string) => {
    const lines = md.split('\n');
    const html: string[] = [];
    let inTable = false;
    let inList = false;

    for (const line of lines) {
      // Table
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        if (!inTable) { html.push('<table class="w-full text-xs border-collapse my-2">'); inTable = true; }
        if (line.includes('---|')) continue; // separator row
        const cells = line.split('|').filter(c => c.trim());
        const tag = html.filter(h => h.includes('<tr')).length === 0 ? 'th' : 'td';
        const cellClass = tag === 'th'
          ? 'px-3 py-1.5 text-left font-bold text-text-muted border-b border-border-subtle uppercase tracking-wider text-[10px]'
          : 'px-3 py-1.5 text-text-secondary border-b border-border-subtle/30';
        html.push(`<tr>${cells.map(c => `<${tag} class="${cellClass}">${c.trim()}</${tag}>`).join('')}</tr>`);
        continue;
      }
      if (inTable && !line.trim().startsWith('|')) { html.push('</table>'); inTable = false; }

      // Close list
      if (inList && !line.trim().startsWith('-') && !line.trim().startsWith('  -')) {
        html.push('</ul>'); inList = false;
      }

      // Headers
      if (line.startsWith('### ')) {
        html.push(`<h3 class="text-sm font-bold text-text-primary mt-3 mb-1 flex items-center gap-2">${line.slice(4)}</h3>`);
      } else if (line.startsWith('## ')) {
        html.push(`<h2 class="text-base font-bold text-text-primary mt-2 mb-2 flex items-center gap-2">${line.slice(3)}</h2>`);
      } else if (line.startsWith('# ')) {
        html.push(`<h1 class="text-lg font-bold text-text-primary mt-2 mb-2">${line.slice(2)}</h1>`);
      }
      // Blockquote
      else if (line.trim().startsWith('>')) {
        const content = line.trim().slice(1).trim();
        const isWarning = content.includes('🔴') || content.includes('Critical');
        html.push(`<blockquote class="border-l-2 ${isWarning ? 'border-intel-red bg-red-500/5' : 'border-intel-blue bg-blue-500/5'} px-3 py-2 my-2 text-xs text-text-secondary rounded-r">${formatInline(content)}</blockquote>`);
      }
      // List items
      else if (line.trim().startsWith('- ') || line.trim().startsWith('  - ')) {
        if (!inList) { html.push('<ul class="space-y-0.5 my-1">'); inList = true; }
        const indent = line.startsWith('  ') ? 'ml-4' : '';
        html.push(`<li class="text-xs text-text-secondary flex gap-1.5 ${indent}"><span class="text-text-muted mt-0.5 shrink-0">›</span><span>${formatInline(line.trim().slice(2))}</span></li>`);
      }
      // Empty line
      else if (!line.trim()) {
        html.push('<div class="h-1"></div>');
      }
      // Normal paragraph
      else {
        html.push(`<p class="text-xs text-text-secondary leading-relaxed">${formatInline(line)}</p>`);
      }
    }
    if (inTable) html.push('</table>');
    if (inList) html.push('</ul>');
    return html.join('\n');
  };

  const formatInline = (text: string) => {
    return text
      .replace(/\*\*(.+?)\*\*/g, '<strong class="text-text-primary font-semibold">$1</strong>')
      .replace(/`([^`]+)`/g, '<code class="px-1 py-0.5 bg-surface rounded text-[10px] font-mono text-intel-blue">$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="text-intel-blue hover:underline">$1</a>');
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-violet-500/20 to-cyan-500/20 border border-violet-500/30 flex items-center justify-center shadow-[0_0_20px_rgba(139,92,246,0.15)]">
            <Bot className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-text-primary tracking-tight">Investigation Copilot</h1>
            <p className="text-[10px] font-mono text-text-muted uppercase tracking-wider">
              ORACLE AI • Natural Language Intelligence Interface
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border-subtle bg-surface/40 text-[10px] font-mono text-text-muted">
            <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#34d399]" />
            9 intents active
          </div>
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto rounded-xl border border-border bg-base/50 backdrop-blur-sm p-4 space-y-4 mb-4 scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 border border-violet-500/20 flex items-center justify-center mb-4 shadow-[0_0_30px_rgba(139,92,246,0.1)]">
              <Sparkles className="w-8 h-8 text-violet-400/60" />
            </div>
            <h2 className="text-sm font-bold text-text-primary mb-1">Ask anything about your investigation</h2>
            <p className="text-xs text-text-muted max-w-md mb-6">
              The Copilot queries the knowledge graph, evidence vault, legal engine, and reasoning traces to provide intelligent answers.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 w-full max-w-2xl">
              {SUGGESTION_CHIPS.map((chip) => {
                const Icon = chip.icon;
                return (
                  <button
                    key={chip.label}
                    onClick={() => handleChipClick(chip.label)}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border-subtle bg-surface/30 text-[11px] text-text-secondary hover:text-text-primary hover:border-violet-500/30 hover:bg-violet-500/5 transition-all duration-200 group"
                  >
                    <Icon className="w-3.5 h-3.5 text-text-muted group-hover:text-violet-400 transition-colors shrink-0" />
                    <span className="truncate text-left">{chip.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={cn("flex gap-3", msg.role === 'user' ? 'justify-end' : 'justify-start')}>
            {msg.role === 'assistant' && (
              <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-violet-500/20 to-cyan-500/20 border border-violet-500/30 flex items-center justify-center shrink-0 mt-0.5">
                <Bot className="w-3.5 h-3.5 text-violet-400" />
              </div>
            )}
            <div className={cn(
              "max-w-[85%] rounded-xl px-4 py-3",
              msg.role === 'user'
                ? "bg-intel-blue/10 border border-intel-blue/20 text-text-primary"
                : "bg-surface/60 border border-border-subtle"
            )}>
              {msg.role === 'user' ? (
                <p className="text-xs font-medium">{msg.content}</p>
              ) : (
                <>
                  {/* Intent badge */}
                  {msg.intent && (
                    <div className="flex items-center gap-2 mb-2">
                      <span className={cn(
                        "px-2 py-0.5 rounded-full text-[9px] font-mono font-bold uppercase border",
                        INTENT_COLORS[msg.intent] || 'text-text-muted bg-surface border-border'
                      )}>
                        {msg.intent.replace(/_/g, ' ')}
                      </span>
                      {msg.confidence !== undefined && (
                        <span className="text-[9px] font-mono text-text-muted">
                          {Math.round(msg.confidence * 100)}% match
                        </span>
                      )}
                      {msg.queryTimeMs !== undefined && (
                        <span className="text-[9px] font-mono text-text-muted flex items-center gap-0.5">
                          <Zap className="w-2.5 h-2.5" /> {msg.queryTimeMs.toFixed(0)}ms
                        </span>
                      )}
                    </div>
                  )}
                  {/* Markdown rendered content */}
                  <div
                    className="copilot-response"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                  />
                  {/* Suggested actions */}
                  {msg.actions && msg.actions.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-border-subtle/30">
                      {msg.actions.map((action, i) => (
                        <button
                          key={i}
                          className="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-mono text-text-muted border border-border-subtle/50 hover:text-intel-blue hover:border-intel-blue/30 transition-colors"
                        >
                          <ChevronRight className="w-2.5 h-2.5" />
                          {action}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
              <div className="mt-1.5 text-[9px] text-text-muted font-mono">
                {msg.timestamp.toLocaleTimeString()}
              </div>
            </div>
            {msg.role === 'user' && (
              <div className="h-7 w-7 rounded-lg bg-elevated border border-border flex items-center justify-center shrink-0 mt-0.5">
                <User className="w-3.5 h-3.5 text-text-secondary" />
              </div>
            )}
          </div>
        ))}

        {/* Thinking indicator */}
        {queryMutation.isPending && (
          <div className="flex gap-3 justify-start">
            <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-violet-500/20 to-cyan-500/20 border border-violet-500/30 flex items-center justify-center shrink-0">
              <Bot className="w-3.5 h-3.5 text-violet-400 animate-pulse" />
            </div>
            <div className="bg-surface/60 border border-border-subtle rounded-xl px-4 py-3 flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 text-violet-400 animate-spin" />
              <span className="text-xs text-text-muted font-mono">Querying ORACLE intelligence engine...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="shrink-0 rounded-xl border border-border bg-surface/80 backdrop-blur-sm p-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-text-muted shrink-0">
            <MessageSquare className="w-3.5 h-3.5 text-violet-400" />
            <span className="hidden sm:inline">COPILOT</span>
          </div>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={activeCaseId
              ? "Ask a question about your investigation..."
              : "Select a case first to start querying..."
            }
            disabled={!activeCaseId || queryMutation.isPending}
            className="flex-1 bg-transparent text-xs text-text-primary placeholder-text-muted focus:outline-none font-mono disabled:opacity-50"
          />
          <Button
            size="sm"
            onClick={handleSend}
            disabled={!input.trim() || !activeCaseId || queryMutation.isPending}
            className="h-8 w-8 p-0 bg-violet-500/20 border border-violet-500/30 hover:bg-violet-500/30 text-violet-400 rounded-lg shrink-0"
          >
            <Send className="w-3.5 h-3.5" />
          </Button>
        </div>
        {!activeCaseId && (
          <p className="text-[10px] text-intel-red/80 font-mono mt-1.5 pl-8">
            ⚠ No active case selected. Use the case selector in the header to activate an investigation.
          </p>
        )}
      </div>
    </div>
  );
}
