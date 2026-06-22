'use client';

import React, { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Dices, Play, Download, Users, Clock, AlertTriangle,
  ChevronRight, CheckCircle2, Loader2, Sparkles, FileDown,
  CreditCard, TrendingUp, Lock, RotateCcw, SlidersHorizontal,
  Boxes, Zap, Target, Shield
} from 'lucide-react';
import { simulationApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

const SCENARIO_ICONS: Record<string, React.ReactNode> = {
  financial_phishing: <CreditCard className="w-6 h-6" />,
  insider_trading: <TrendingUp className="w-6 h-6" />,
  ransomware_extortion: <Lock className="w-6 h-6" />,
};

const SCENARIO_GRADIENTS: Record<string, string> = {
  financial_phishing: 'from-amber-500/15 to-orange-500/15 border-amber-500/30 hover:border-amber-400/50',
  insider_trading: 'from-emerald-500/15 to-teal-500/15 border-emerald-500/30 hover:border-emerald-400/50',
  ransomware_extortion: 'from-rose-500/15 to-red-500/15 border-rose-500/30 hover:border-rose-400/50',
};

const SCENARIO_ICON_COLORS: Record<string, string> = {
  financial_phishing: 'text-amber-400',
  insider_trading: 'text-emerald-400',
  ransomware_extortion: 'text-rose-400',
};

const DIFFICULTY_BADGES: Record<string, string> = {
  beginner: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  intermediate: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  advanced: 'text-rose-400 bg-rose-500/10 border-rose-500/30',
};

interface SimResult {
  case_id: string;
  scenario: string;
  suspects_created: number;
  artifacts_created: number;
  events_created: number;
  contradictions_planted: number;
  summary_md: string;
  download_url: string;
}

export default function SimulationPage() {
  const { setActiveCase } = useCaseStore();
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);
  const [suspects, setSuspects] = useState(2);
  const [timelineDays, setTimelineDays] = useState(14);
  const [contradictionDensity, setContradictionDensity] = useState<'low' | 'medium' | 'high'>('medium');
  const [result, setResult] = useState<SimResult | null>(null);

  const { data: scenariosData } = useQuery({
    queryKey: ['simulation-scenarios'],
    queryFn: simulationApi.getScenarios,
  });

  const scenarios = scenariosData?.scenarios || [];

  const simulateMutation = useMutation({
    mutationFn: () => simulationApi.simulate({
      scenario: selectedScenario!,
      suspects,
      timeline_days: timelineDays,
      contradiction_density: contradictionDensity,
    }),
    onSuccess: (data) => {
      setResult(data);
      // Auto-activate the simulated case
      setActiveCase({
        case_id: data.case_id,
        case_type: `SIM_${data.scenario.toUpperCase()}`,
        status: 'under_investigation',
        classification_tag: 'evidentiary',
        created_by: 'SIM_ENGINE',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    },
  });

  // Simple markdown renderer for the summary
  const renderSummary = (md: string) => {
    return md.split('\n').map((line, i) => {
      if (line.startsWith('## ')) return <h2 key={i} className="text-base font-bold text-text-primary mt-3 mb-2">{line.slice(3)}</h2>;
      if (line.startsWith('### ')) return <h3 key={i} className="text-sm font-bold text-text-primary mt-3 mb-1">{line.slice(4)}</h3>;
      if (line.startsWith('- **')) {
        const match = line.match(/- \*\*(.+?)\*\*:?\s*(.*)/);
        if (match) return (
          <div key={i} className="flex gap-2 text-xs py-0.5">
            <span className="text-text-muted">›</span>
            <span><strong className="text-text-primary">{match[1]}</strong>{match[2] ? `: ${match[2]}` : ''}</span>
          </div>
        );
      }
      if (line.match(/^\d+\.\s/)) {
        return <div key={i} className="text-xs text-text-secondary py-0.5 ml-2">{line}</div>;
      }
      if (!line.trim()) return <div key={i} className="h-1" />;
      return <p key={i} className="text-xs text-text-secondary">{line}</p>;
    });
  };

  return (
    <div className="max-w-5xl mx-auto space-y-8">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-rose-500/20 to-amber-500/20 border border-rose-500/30 flex items-center justify-center shadow-[0_0_20px_rgba(244,63,94,0.15)]">
            <Dices className="w-5 h-5 text-rose-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-text-primary tracking-tight">Crime Simulation Lab</h1>
            <p className="text-[10px] font-mono text-text-muted uppercase tracking-wider">
              Synthetic Investigation Generator • Training & Benchmarking
            </p>
          </div>
        </div>
        {result && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setResult(null); setSelectedScenario(null); }}
            className="text-xs font-mono gap-1.5 border-border-subtle text-text-secondary hover:text-text-primary"
          >
            <RotateCcw className="w-3 h-3" /> New Simulation
          </Button>
        )}
      </div>

      {!result ? (
        <>
          {/* Scenario Selection */}
          <div>
            <h2 className="text-xs font-mono font-bold text-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
              <Target className="w-3.5 h-3.5" /> Select Scenario Template
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {scenarios.map((s: any) => (
                <button
                  key={s.id}
                  onClick={() => setSelectedScenario(s.id)}
                  className={cn(
                    "relative rounded-xl border p-5 text-left transition-all duration-300 group bg-gradient-to-br",
                    SCENARIO_GRADIENTS[s.id] || 'from-surface to-surface border-border',
                    selectedScenario === s.id && 'ring-2 ring-intel-blue shadow-[0_0_20px_rgba(74,158,255,0.15)]'
                  )}
                >
                  {selectedScenario === s.id && (
                    <div className="absolute top-3 right-3">
                      <CheckCircle2 className="w-4 h-4 text-intel-blue" />
                    </div>
                  )}
                  <div className={cn(
                    "h-12 w-12 rounded-xl flex items-center justify-center mb-3 bg-obsidian/40 border border-border-subtle/50",
                    SCENARIO_ICON_COLORS[s.id]
                  )}>
                    {SCENARIO_ICONS[s.id] || <Boxes className="w-6 h-6" />}
                  </div>
                  <div className="flex items-center gap-2 mb-1.5">
                    <h3 className="text-sm font-bold text-text-primary">{s.icon} {s.name}</h3>
                    <span className={cn(
                      "px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase border",
                      DIFFICULTY_BADGES[s.difficulty] || ''
                    )}>
                      {s.difficulty}
                    </span>
                  </div>
                  <p className="text-[11px] text-text-muted leading-relaxed mb-3">{s.description}</p>
                  <div className="flex flex-wrap gap-1">
                    {s.evidence_types?.map((et: string) => (
                      <span key={et} className="px-1.5 py-0.5 rounded text-[9px] font-mono text-text-muted bg-obsidian/30 border border-border-subtle/30">
                        {et}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
              {/* Fallback when API is unavailable */}
              {scenarios.length === 0 && (
                <>
                  {[
                    { id: 'financial_phishing', name: '💳 Financial Phishing', desc: 'Spoofed banking domain, OTP bypass, ATM withdrawals with GPS logs', diff: 'beginner' },
                    { id: 'insider_trading', name: '📈 Insider Trading', desc: 'Employee tips off broker, encrypted chat leaks, demat trade records', diff: 'intermediate' },
                    { id: 'ransomware_extortion', name: '🔐 Ransomware Extortion', desc: 'TOR-based C2, crypto ransom demands, network intrusion logs', diff: 'advanced' },
                  ].map(s => (
                    <button
                      key={s.id}
                      onClick={() => setSelectedScenario(s.id)}
                      className={cn(
                        "relative rounded-xl border p-5 text-left transition-all duration-300 group bg-gradient-to-br",
                        SCENARIO_GRADIENTS[s.id],
                        selectedScenario === s.id && 'ring-2 ring-intel-blue shadow-[0_0_20px_rgba(74,158,255,0.15)]'
                      )}
                    >
                      {selectedScenario === s.id && (
                        <div className="absolute top-3 right-3">
                          <CheckCircle2 className="w-4 h-4 text-intel-blue" />
                        </div>
                      )}
                      <div className={cn(
                        "h-12 w-12 rounded-xl flex items-center justify-center mb-3 bg-obsidian/40 border border-border-subtle/50",
                        SCENARIO_ICON_COLORS[s.id]
                      )}>
                        {SCENARIO_ICONS[s.id]}
                      </div>
                      <h3 className="text-sm font-bold text-text-primary mb-1">{s.name}</h3>
                      <span className={cn("px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase border mb-2 inline-block", DIFFICULTY_BADGES[s.diff])}>{s.diff}</span>
                      <p className="text-[11px] text-text-muted leading-relaxed">{s.desc}</p>
                    </button>
                  ))}
                </>
              )}
            </div>
          </div>

          {/* Simulation Controls */}
          {selectedScenario && (
            <div className="rounded-xl border border-border bg-surface/30 p-6 space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
              <h2 className="text-xs font-mono font-bold text-text-muted uppercase tracking-wider flex items-center gap-2">
                <SlidersHorizontal className="w-3.5 h-3.5" /> Simulation Parameters
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Suspects */}
                <div className="space-y-2">
                  <label className="text-[11px] font-mono font-bold text-text-secondary flex items-center gap-1.5">
                    <Users className="w-3 h-3 text-text-muted" /> Suspects Count
                  </label>
                  <div className="flex items-center gap-2">
                    {[1, 2, 3, 4, 5].map(n => (
                      <button
                        key={n}
                        onClick={() => setSuspects(n)}
                        className={cn(
                          "w-9 h-9 rounded-lg border text-xs font-bold transition-all",
                          suspects === n
                            ? "bg-intel-blue/20 border-intel-blue/50 text-intel-blue shadow-[0_0_10px_rgba(74,158,255,0.15)]"
                            : "bg-surface border-border-subtle text-text-muted hover:text-text-primary hover:border-border"
                        )}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Timeline */}
                <div className="space-y-2">
                  <label className="text-[11px] font-mono font-bold text-text-secondary flex items-center gap-1.5">
                    <Clock className="w-3 h-3 text-text-muted" /> Timeline Duration (days)
                  </label>
                  <div className="flex items-center gap-2">
                    {[7, 14, 30, 60, 90].map(d => (
                      <button
                        key={d}
                        onClick={() => setTimelineDays(d)}
                        className={cn(
                          "px-3 h-9 rounded-lg border text-xs font-bold transition-all",
                          timelineDays === d
                            ? "bg-intel-blue/20 border-intel-blue/50 text-intel-blue shadow-[0_0_10px_rgba(74,158,255,0.15)]"
                            : "bg-surface border-border-subtle text-text-muted hover:text-text-primary hover:border-border"
                        )}
                      >
                        {d}d
                      </button>
                    ))}
                  </div>
                </div>

                {/* Contradiction Density */}
                <div className="space-y-2">
                  <label className="text-[11px] font-mono font-bold text-text-secondary flex items-center gap-1.5">
                    <AlertTriangle className="w-3 h-3 text-text-muted" /> Contradiction Density
                  </label>
                  <div className="flex items-center gap-2">
                    {(['low', 'medium', 'high'] as const).map(d => (
                      <button
                        key={d}
                        onClick={() => setContradictionDensity(d)}
                        className={cn(
                          "px-3 h-9 rounded-lg border text-xs font-bold capitalize transition-all",
                          contradictionDensity === d
                            ? d === 'high' ? 'bg-rose-500/20 border-rose-500/50 text-rose-400' :
                              d === 'medium' ? 'bg-amber-500/20 border-amber-500/50 text-amber-400' :
                              'bg-emerald-500/20 border-emerald-500/50 text-emerald-400'
                            : "bg-surface border-border-subtle text-text-muted hover:text-text-primary hover:border-border"
                        )}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Generate Button */}
              <div className="pt-2">
                <Button
                  onClick={() => simulateMutation.mutate()}
                  disabled={simulateMutation.isPending}
                  className="w-full h-12 bg-gradient-to-r from-rose-500/20 to-amber-500/20 border border-rose-500/30 hover:from-rose-500/30 hover:to-amber-500/30 text-text-primary font-bold text-sm rounded-xl transition-all duration-300 gap-2"
                >
                  {simulateMutation.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span className="font-mono">Generating Investigation...</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 text-rose-400" />
                      <span>Generate Synthetic Investigation</span>
                      <Sparkles className="w-4 h-4 text-amber-400" />
                    </>
                  )}
                </Button>
                {simulateMutation.isError && (
                  <p className="text-[11px] text-intel-red font-mono mt-2 text-center">
                    ⚠ {(simulateMutation.error as any)?.response?.data?.detail || 'Simulation failed. Ensure the backend is running.'}
                  </p>
                )}
              </div>
            </div>
          )}
        </>
      ) : (
        /* Results Panel */
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">

          {/* Stats Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: 'Suspects', value: result.suspects_created, icon: Users, color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20' },
              { label: 'Artifacts', value: result.artifacts_created, icon: FileDown, color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
              { label: 'Events', value: result.events_created, icon: Zap, color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' },
              { label: 'Contradictions', value: result.contradictions_planted, icon: AlertTriangle, color: 'text-rose-400 bg-rose-500/10 border-rose-500/20' },
            ].map(stat => {
              const Icon = stat.icon;
              return (
                <div key={stat.label} className={cn("rounded-xl border p-4", stat.color)}>
                  <div className="flex items-center justify-between mb-2">
                    <Icon className="w-4 h-4" />
                    <span className="text-2xl font-bold">{stat.value}</span>
                  </div>
                  <p className="text-[10px] font-mono font-bold uppercase tracking-wider opacity-70">{stat.label}</p>
                </div>
              );
            })}
          </div>

          {/* Case ID & Actions */}
          <div className="rounded-xl border border-border bg-surface/30 p-4 flex items-center justify-between">
            <div>
              <p className="text-[10px] font-mono text-text-muted uppercase tracking-wider">Generated Case ID</p>
              <p className="text-sm font-mono font-bold text-intel-blue">{result.case_id}</p>
              <p className="text-[10px] font-mono text-emerald-400 flex items-center gap-1 mt-0.5">
                <CheckCircle2 className="w-3 h-3" /> Auto-activated in workspace
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.open(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}${result.download_url}`, '_blank')}
                className="text-xs font-mono gap-1.5 border-border-subtle text-text-secondary hover:text-text-primary"
              >
                <Download className="w-3 h-3" /> Download Evidence ZIP
              </Button>
            </div>
          </div>

          {/* Summary */}
          <div className="rounded-xl border border-border bg-base/50 p-6">
            <h2 className="text-xs font-mono font-bold text-text-muted uppercase tracking-wider mb-4 flex items-center gap-2">
              <Shield className="w-3.5 h-3.5" /> Investigation Summary
            </h2>
            <div className="space-y-0.5">
              {renderSummary(result.summary_md)}
            </div>
          </div>

          {/* Quick Navigation */}
          <div className="rounded-xl border border-border bg-surface/30 p-4">
            <h3 className="text-xs font-mono font-bold text-text-muted uppercase tracking-wider mb-3">Next Steps</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {[
                { label: 'Open Dashboard', path: '/' },
                { label: 'Knowledge Graph', path: '/graph' },
                { label: 'Evidence Vault', path: '/evidence' },
                { label: 'Copilot', path: '/copilot' },
                { label: 'Timeline', path: '/timeline' },
                { label: 'Contradictions', path: '/contradictions' },
                { label: 'Theory Workspace', path: '/theory' },
                { label: 'Court Readiness', path: '/legal/court' },
              ].map(nav => (
                <a
                  key={nav.path}
                  href={nav.path}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border-subtle bg-surface/20 text-[11px] font-mono text-text-secondary hover:text-intel-blue hover:border-intel-blue/30 transition-all"
                >
                  <ChevronRight className="w-3 h-3 text-text-muted" />
                  {nav.label}
                </a>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
