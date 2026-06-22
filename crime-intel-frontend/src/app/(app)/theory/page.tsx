'use client';

import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { reasoningApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { useSelectionStore } from '@/lib/store/selection.store';
import { cn } from '@/lib/utils';
import { 
  IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, IntelCardFooter,
  EmptyState, ProbabilityDisplay
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { 
  Brain, FileText, Play, Plus, RefreshCw, Layers, ShieldAlert,
  GitPullRequest, Compass, BarChart4, Loader2, Sparkles, Terminal, X
} from 'lucide-react';

export default function TheoryEngineWorkspace() {
  const queryClient = useQueryClient();
  const { activeCaseId } = useCaseStore();
  const { panelSizes, setPanelSizes } = useWorkspaceStore();
  const { select } = useSelectionStore();
  const [selectedHypothesisId, setSelectedHypothesisId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'explain' | 'sensitivity' | 'challenge' | 'hpl'>('explain');
  
  // New theory form
  const [showSpawnForm, setShowSpawnForm] = useState(false);
  const [narrative, setNarrative] = useState('');
  const [scenarioType, setScenarioType] = useState('Cyber Theft');

  // Query: List hypotheses
  const { data: hypotheses = [], isLoading, refetch } = useQuery({
    queryKey: ['hypotheses', activeCaseId],
    queryFn: () => reasoningApi.listHypotheses(activeCaseId!),
    enabled: !!activeCaseId,
  });

  // Query: Explain selected hypothesis
  const { data: explanation, isLoading: isLoadingExplanation } = useQuery({
    queryKey: ['hypothesis-explain', selectedHypothesisId],
    queryFn: () => reasoningApi.explainHypothesis(activeCaseId!, selectedHypothesisId!),
    enabled: !!activeCaseId && !!selectedHypothesisId && activeTab === 'explain',
  });

  // Query: Sensitivity analysis
  const { data: sensitivity = [], isLoading: isLoadingSensitivity } = useQuery({
    queryKey: ['hypothesis-sensitivity', selectedHypothesisId],
    queryFn: () => reasoningApi.getSensitivity(activeCaseId!, selectedHypothesisId!),
    enabled: !!activeCaseId && !!selectedHypothesisId && activeTab === 'sensitivity',
  });

  // Query: Challenge analysis
  const { data: challenge, isLoading: isLoadingChallenge } = useQuery({
    queryKey: ['hypothesis-challenge', selectedHypothesisId],
    queryFn: () => reasoningApi.getChallenge(activeCaseId!, selectedHypothesisId!),
    enabled: !!activeCaseId && !!selectedHypothesisId && activeTab === 'challenge',
  });

  // Mutation: Spawn new hypothesis
  const spawnMutation = useMutation({
    mutationFn: (data: { narrative: string; scenario_type: string }) => 
      reasoningApi.spawnHypothesis(activeCaseId!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hypotheses', activeCaseId] });
      setNarrative('');
      setShowSpawnForm(false);
    }
  });

  const handleSpawn = (e: React.FormEvent) => {
    e.preventDefault();
    spawnMutation.mutate({ narrative, scenario_type: scenarioType });
  };

  const selectedHypothesis = hypotheses.find(h => h.id === selectedHypothesisId);

  // Synchronize selection store
  const handleSelectHypothesis = (id: string) => {
    setSelectedHypothesisId(id);
    const hyp = hypotheses.find(h => h.id === id);
    if (hyp) {
      select({
        id: hyp.id,
        type: 'theory',
        name: hyp.narrative,
        metadata: {
          probability: hyp.probability
        }
      });
    }
  };

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the cognitive theory workspace."
      />
    );
  }

  return (
    <div className="h-full w-full flex flex-col overflow-hidden bg-base">
      
      {/* 1. ACTIONS HEADER */}
      <div className="h-10 border-b border-border bg-surface px-4 flex items-center justify-between shrink-0 select-none text-[10px] font-mono">
        <div className="flex items-center gap-1.5 text-text-secondary">
          <Brain className="w-3.5 h-3.5 text-intel-magenta" />
          <span>ORACLE COGNITIVE THEORY ENGINE</span>
        </div>

        <div className="flex items-center gap-2">
          <Button 
            variant="secondary"
            onClick={() => refetch()}
            className="h-6 px-2.5 font-mono text-[9px] border-border-subtle"
          >
            <RefreshCw className="w-3 h-3" />
          </Button>
          <Button 
            onClick={() => setShowSpawnForm(true)}
            className="h-6 px-3 bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-[9px] gap-1 shrink-0 animate-pulse"
          >
            <Sparkles className="w-3 h-3" />
            <span>SPAWN COGNITIVE THEORY</span>
          </Button>
        </div>
      </div>

      {/* 2. SPLIT RESIZABLE WORKSPACE AREA */}
      <div className="flex-1 min-h-0 w-full relative">
        <PanelGroup 
          orientation="horizontal" 
          onLayoutChanged={(layout) => setPanelSizes('theory-engine', Object.values(layout))}
        >
          {/* Left Panel: Hypotheses Catalog */}
          <Panel id="te-left" defaultSize={panelSizes['theory-engine'][0]} minSize={25} className="h-full flex flex-col overflow-hidden bg-base">
            <div className="p-3 border-b border-border bg-surface/40 flex items-center justify-between shrink-0 select-none text-[10px] font-mono font-bold text-text-secondary uppercase">
              <span>Theories Catalog ({hypotheses.length})</span>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-thin">
              {isLoading ? (
                <div className="space-y-2">
                  {[1, 2].map((_, i) => (
                    <div key={i} className="h-20 rounded bg-surface animate-pulse" />
                  ))}
                </div>
              ) : hypotheses.length === 0 ? (
                <div className="text-center py-8 text-text-muted font-mono text-[9px] border border-dashed border-border rounded bg-surface/5">
                  No hypotheses defined. Spawn a new theory.
                </div>
              ) : (
                hypotheses.map((h) => {
                  const isSelected = h.id === selectedHypothesisId;
                  return (
                    <div
                      key={h.id}
                      onClick={() => handleSelectHypothesis(h.id)}
                      className={cn(
                        "p-3 rounded border transition-all duration-150 cursor-pointer flex flex-col gap-2.5",
                        isSelected 
                          ? "bg-intel-magenta-dim/10 border-intel-magenta/50 shadow-sm" 
                          : "bg-surface border-border-subtle hover:border-border/60"
                      )}
                    >
                      <p className="text-[10.5px] font-bold text-text-primary leading-snug line-clamp-2">
                        {h.narrative}
                      </p>
                      
                      <div className="flex justify-between items-center border-t border-border-subtle/30 pt-2 font-mono text-[8px]">
                        <span className="text-text-muted">ID: {h.id.slice(0, 8)}...</span>
                        {h.probability !== undefined && (
                          <div className="flex items-center gap-1 font-mono text-[9px]">
                            <span className="text-text-secondary">Prob:</span>
                            <span className="font-bold text-intel-magenta">{Math.round(h.probability * 100)}%</span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle className="w-[1px] hover:w-[3px] bg-border hover:bg-intel-blue transition-all duration-150 relative cursor-col-resize h-full" />

          {/* Right Panel: Theory details */}
          <Panel id="te-right" defaultSize={panelSizes['theory-engine'][1]} minSize={40} className="h-full flex flex-col overflow-hidden bg-surface border-l border-border">
            {selectedHypothesisId && selectedHypothesis ? (
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* Header info */}
                <div className="p-4 border-b border-border flex flex-col gap-3 shrink-0">
                  <div className="flex justify-between items-start gap-4">
                    <div className="min-w-0">
                      <span className="text-[8px] font-mono font-bold text-intel-magenta uppercase tracking-wider bg-intel-magenta-dim/15 px-1.5 py-0.5 rounded border border-intel-magenta/20">
                        Cognitive Hypothesis
                      </span>
                      <h3 className="text-xs font-bold text-text-primary mt-2 leading-snug font-sans">
                        {selectedHypothesis.narrative}
                      </h3>
                    </div>
                    {selectedHypothesis.probability !== undefined && (
                      <ProbabilityDisplay value={selectedHypothesis.probability} confidence={selectedHypothesis.confidence_in_probability} />
                    )}
                  </div>

                  {/* Sub tabs */}
                  <div className="flex gap-1 border-b border-border-subtle/50 pb-px">
                    {(['explain', 'sensitivity', 'challenge', 'hpl'] as const).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={cn(
                          "px-3 py-1.5 border-b-2 text-[10px] font-mono font-bold uppercase transition-all cursor-pointer",
                          activeTab === tab 
                            ? "border-intel-magenta text-intel-magenta" 
                            : "border-transparent text-text-secondary hover:text-text-primary"
                        )}
                      >
                        {tab}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Sub Tab contents */}
                <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
                  
                  {/* Tab 1: EXPLAIN */}
                  {activeTab === 'explain' && (
                    <div className="space-y-3">
                      <h4 className="text-[9px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                        Deductive Logical Step Traces
                      </h4>
                      {isLoadingExplanation ? (
                        <div className="space-y-2">
                          <div className="h-16 bg-base rounded animate-pulse" />
                        </div>
                      ) : explanation?.explanation ? (
                        <div className="bg-base/40 p-3.5 rounded border border-border-subtle select-all">
                          <p className="text-[10.5px] text-text-secondary leading-relaxed font-sans whitespace-pre-line">
                            {explanation.explanation}
                          </p>
                        </div>
                      ) : (
                        <div className="text-center py-8 text-text-muted font-mono text-[9px]">
                          No explanations generated.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Tab 2: SENSITIVITY */}
                  {activeTab === 'sensitivity' && (
                    <div className="space-y-3">
                      <h4 className="text-[9px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                        Evidence Sensitivity Matrix (Entropy Shifts)
                      </h4>
                      {isLoadingSensitivity ? (
                        <div className="space-y-2">
                          <div className="h-16 bg-base rounded animate-pulse" />
                        </div>
                      ) : sensitivity.length > 0 ? (
                        <div className="space-y-2 text-[10px] font-mono">
                          {sensitivity.map((item: any, idx: number) => (
                            <div key={idx} className="flex justify-between items-center p-2.5 bg-base/40 border border-border-subtle rounded">
                              <div className="flex flex-col gap-0.5">
                                <span className="font-bold text-text-primary">{item.evidence_name || 'Evidence Item'}</span>
                                <span className="text-[8px] text-text-muted">Type: {item.evidence_type}</span>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className="text-[8px] text-text-muted">Entropy:</span>
                                <span className="font-bold text-intel-blue">{item.weight?.toFixed(3) || '0.150'}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-8 text-text-muted font-mono text-[9px]">
                          No sensitivity models calculated for this hypothesis.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Tab 3: CHALLENGE */}
                  {activeTab === 'challenge' && (
                    <div className="space-y-3">
                      <h4 className="text-[9px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                        Critical Contradiction Stress Testing
                      </h4>
                      {isLoadingChallenge ? (
                        <div className="space-y-2">
                          <div className="h-16 bg-base rounded animate-pulse" />
                        </div>
                      ) : challenge ? (
                        <div className="p-3 bg-intel-red-dim/10 border border-intel-red/20 rounded-lg space-y-2 text-[10px] font-mono">
                          <div className="flex items-center gap-1.5 text-intel-red">
                            <ShieldAlert className="w-4 h-4" />
                            <span className="font-bold uppercase tracking-wider">Contradiction Violations</span>
                          </div>
                          <p className="text-text-secondary leading-relaxed font-sans">
                            {challenge.summary || "No critical logical contradictions found violating this scenario's predicates."}
                          </p>
                        </div>
                      ) : (
                        <div className="text-center py-8 text-text-muted font-mono text-[9px]">
                          No contradiction analysis available.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Tab 4: HPL */}
                  {activeTab === 'hpl' && (
                    <div className="space-y-3">
                      <h4 className="text-[9px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                        HPL Predicate Specifications
                      </h4>
                      <div className="bg-base/80 p-3.5 rounded border border-border-subtle font-mono text-[10px] text-intel-green space-y-1 overflow-x-auto min-h-[120px] relative select-all">
                        <Terminal className="absolute right-3 top-3 w-3.5 h-3.5 text-text-muted" />
                        <div># Predicate list for {selectedHypothesis.id.slice(0, 8)}</div>
                        {selectedHypothesis.predicates && selectedHypothesis.predicates.length > 0 ? (
                          selectedHypothesis.predicates.map((pred, i) => (
                            <div key={i}>{pred}</div>
                          ))
                        ) : (
                          <>
                            <div>EXISTS Person(name == Defendant)</div>
                            <div>EXISTS Device(device_type == Laptop)</div>
                            <div>LINKED(Person, Device, OWNS)</div>
                          </>
                        )}
                      </div>
                    </div>
                  )}

                </div>
              </div>
            ) : (
              <EmptyState 
                title="No theory selected" 
                description="Click on any cognitive theory/hypothesis on the left to inspect explain logs, sensitivity metrics, and stress challenges."
                icon={Brain}
              />
            )}
          </Panel>
        </PanelGroup>
      </div>

      {/* Spawn Dialog Slideover Overlay */}
      {showSpawnForm && (
        <>
          <div 
            className="fixed inset-0 bg-obsidian/75 backdrop-blur-sm z-40 animate-in fade-in"
            onClick={() => setShowSpawnForm(false)}
          />
          <div className="fixed top-0 right-0 h-full w-full max-w-sm bg-overlay border-l border-border shadow-2xl z-50 p-5 flex flex-col justify-between animate-in slide-in-from-right duration-250 font-mono text-[10px]">
            <div className="space-y-5">
              <div className="flex justify-between items-center border-b border-border-subtle pb-3">
                <div>
                  <h3 className="text-xs font-bold text-text-primary flex items-center gap-2">
                    <Brain className="w-4 h-4 text-intel-magenta" />
                    <span>Spawn Causal Hypothesis</span>
                  </h3>
                </div>
                <button 
                  onClick={() => setShowSpawnForm(false)}
                  className="text-text-secondary hover:text-text-primary p-0.5"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleSpawn} className="space-y-4">
                <div className="space-y-1">
                  <label className="text-[8px] font-bold uppercase tracking-wider text-text-secondary">
                    Theory Narrative
                  </label>
                  <textarea
                    value={narrative}
                    onChange={(e) => setNarrative(e.target.value)}
                    className="w-full h-24 bg-base border border-border rounded p-2 text-[10px] text-text-primary focus:outline-none focus:border-intel-blue/50 resize-none font-sans"
                    placeholder="e.g. Defendant compromised root credential during session leak..."
                    required
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-[8px] font-bold uppercase tracking-wider text-text-secondary">
                    Scenario Category
                  </label>
                  <select
                    value={scenarioType}
                    onChange={(e) => setScenarioType(e.target.value)}
                    className="w-full bg-base border border-border rounded px-2.5 py-1.5 text-[10px] text-text-primary focus:outline-none focus:border-intel-blue/50"
                  >
                    <option value="Cyber Theft">Cyber Espionage</option>
                    <option value="Financial Laundering">Financial Laundering</option>
                    <option value="Insider Intrusion">Insider Intrusion</option>
                  </select>
                </div>

                <Button 
                  type="submit" 
                  className="w-full bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-bold text-[10px] mt-4 py-2 rounded shadow-md"
                  disabled={spawnMutation.isPending}
                >
                  {spawnMutation.isPending ? "SPAWNING..." : "CONFIRM SPAWN"}
                </Button>
              </form>
            </div>
          </div>
        </>
      )}

    </div>
  );
}
