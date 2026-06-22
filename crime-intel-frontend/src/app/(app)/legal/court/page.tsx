'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { courtApi, legalApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { useSelectionStore } from '@/lib/store/selection.store';
import { 
  IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, 
  EmptyState, ConfidenceBar 
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { Hammer, Play, RefreshCw, Loader2, CheckCircle2, ShieldAlert, FileSignature, FileText, Scale } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function CourtPrepWorkspace() {
  const queryClient = useQueryClient();
  const { activeCaseId } = useCaseStore();
  const { panelSizes, setPanelSizes } = useWorkspaceStore();
  const { select } = useSelectionStore();

  // Active sub-tab on the left: 'admissibility' or 'chargesheet'
  const [activeSubTab, setActiveSubTab] = useState<'admissibility' | 'chargesheet'>('admissibility');

  // Query: Court Admissibility Readiness
  const { data: readiness, isLoading: isLoadingReadiness, refetch: refetchReadiness, isRefetching: isRefetchingReadiness } = useQuery({
    queryKey: ['court-readiness', activeCaseId],
    queryFn: () => courtApi.getCourtReadiness(activeCaseId!),
    enabled: !!activeCaseId,
  });

  // Query: Chargesheet Sandbox Readiness
  const { data: chargesheet, isLoading: isLoadingChargesheet, refetch: refetchChargesheet, isRefetching: isRefetchingChargesheet } = useQuery({
    queryKey: ['chargesheet-readiness', activeCaseId],
    queryFn: () => legalApi.getChargesheetReadiness(activeCaseId!),
    enabled: !!activeCaseId,
  });

  // Mutation: Run Defense Simulation
  const simulateMutation = useMutation({
    mutationFn: () => courtApi.runCourtReadiness(activeCaseId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['court-readiness', activeCaseId] });
    }
  });

  // Mutation: Generate Chargesheet Report
  const generateChargesheetMutation = useMutation({
    mutationFn: () => legalApi.generateChargesheetReadiness(activeCaseId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chargesheet-readiness', activeCaseId] });
    }
  });

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the court simulation & chargesheet sandbox."
      />
    );
  }

  const handleSelectChecklist = (requirement: string, passed: boolean) => {
    select({
      id: requirement,
      type: 'legal',
      name: requirement,
      metadata: {
        passed,
        context: 'court_readiness_checklist'
      }
    });
  };

  const handleSelectAllegation = (allegation: string) => {
    select({
      id: allegation,
      type: 'legal',
      name: `Allegation: ${allegation.slice(0, 30)}...`,
      metadata: {
        allegation,
        context: 'unsupported_chargesheet_allegation'
      }
    });
  };

  return (
    <div className="h-full w-full flex flex-col overflow-hidden bg-base">
      
      {/* 1. TOP ACTIONS HEADER */}
      <div className="h-10 border-b border-border bg-surface px-4 flex items-center justify-between shrink-0 select-none text-[10px] font-mono">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-text-secondary">
            <Hammer className="w-3.5 h-3.5 text-intel-blue" />
            <span className="font-bold">COURT PREPARATION & PROSECUTION SUFFICENCY</span>
          </div>

          <div className="flex gap-1 border-l border-border-subtle pl-4">
            <button
              onClick={() => setActiveSubTab('admissibility')}
              className={cn(
                "px-2.5 py-0.5 rounded transition-all",
                activeSubTab === 'admissibility' ? "bg-elevated text-intel-blue border border-border" : "text-text-secondary hover:text-text-primary"
              )}
            >
              ADMISSIBILITY TESTER
            </button>
            <button
              onClick={() => setActiveSubTab('chargesheet')}
              className={cn(
                "px-2.5 py-0.5 rounded transition-all",
                activeSubTab === 'chargesheet' ? "bg-elevated text-intel-blue border border-border" : "text-text-secondary hover:text-text-primary"
              )}
            >
              CHARGESHEET SANDBOX
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button 
            variant="secondary"
            onClick={() => {
              refetchReadiness();
              refetchChargesheet();
            }}
            disabled={isLoadingReadiness || isRefetchingReadiness || isLoadingChargesheet || isRefetchingChargesheet}
            className="h-6 px-2.5 font-mono text-[9px] border-border-subtle"
          >
            <RefreshCw className={isRefetchingReadiness || isRefetchingChargesheet ? "w-3 h-3 animate-spin" : "w-3 h-3"} />
          </Button>

          {activeSubTab === 'admissibility' ? (
            <Button 
              onClick={() => simulateMutation.mutate()}
              disabled={simulateMutation.isPending}
              className="h-6 px-3 bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-[9px] gap-1 shrink-0"
            >
              {simulateMutation.isPending ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : "RUN DEFENSE STRESS SIMULATION"}
            </Button>
          ) : (
            <Button 
              onClick={() => generateChargesheetMutation.mutate()}
              disabled={generateChargesheetMutation.isPending}
              className="h-6 px-3 bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-[9px] gap-1 shrink-0"
            >
              {generateChargesheetMutation.isPending ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : "GENERATE READINESS REPORT"}
            </Button>
          )}
        </div>
      </div>

      {/* 2. SPLIT RESIZABLE WORKSPACE AREA */}
      <div className="flex-1 min-h-0 w-full relative">
        <PanelGroup 
          orientation="horizontal" 
          onLayoutChanged={(layout) => setPanelSizes('court-prep', Object.values(layout))}
        >
          {/* Left Panel: Scorecards / Strength metrics */}
          <Panel id="cp-left" defaultSize={panelSizes['court-prep']?.[0] || 50} minSize={30} className="h-full flex flex-col overflow-hidden bg-base">
            <div className="p-3 border-b border-border bg-surface/40 flex items-center justify-between shrink-0 select-none text-[10px] font-mono font-bold text-text-secondary uppercase">
              <span>{activeSubTab === 'admissibility' ? 'Admissibility Scorecard' : 'Evidentiary Sufficiency'}</span>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
              {activeSubTab === 'admissibility' ? (
                readiness ? (
                  <div className="space-y-4">
                    <div className="bg-surface border border-border rounded p-4 space-y-4">
                      <div className="space-y-1.5">
                        <span className="text-[9px] font-mono font-bold text-text-secondary uppercase">Overall Admissibility Score</span>
                        <ConfidenceBar value={readiness.overall_score || 80} showLabel />
                      </div>
                      
                      <div className="space-y-1.5">
                        <span className="text-[9px] font-mono font-bold text-text-secondary uppercase">Evidence Strength Metric</span>
                        <ConfidenceBar value={readiness.evidence_strength_score || 75} showLabel />
                      </div>
                    </div>

                    <div className="bg-obsidian/45 border border-border-subtle rounded p-3 text-[9px] font-mono text-text-secondary leading-relaxed">
                      📢 <span className="font-bold text-text-primary">Judicial Compliance Notice</span>: The overall court admissibility indices are generated using recursive audits of the evidentiary chain. Gaps in witness or metadata validation directly depress strength metrics.
                    </div>
                  </div>
                ) : (
                  <div className="py-12">
                    <EmptyState 
                      title="No evaluations simulated" 
                      description="Initialize court stress tests to calculate admissibility indices and checklist parameters."
                      icon={Hammer}
                    />
                  </div>
                )
              ) : (
                chargesheet ? (
                  <div className="space-y-4">
                    <div className="bg-surface border border-border rounded p-4 space-y-4">
                      <div className="flex justify-between items-start">
                        <div className="space-y-1">
                          <span className="text-[8px] font-mono font-bold text-text-secondary uppercase">Readiness Assessment</span>
                          <h4 className="text-sm font-bold text-text-primary flex items-center gap-1.5 font-mono">
                            <FileSignature className="w-4 h-4 text-intel-blue" />
                            <span>Tier Status</span>
                          </h4>
                        </div>
                        <span className={cn(
                          "px-2 py-0.5 rounded text-[9px] font-mono font-bold border",
                          chargesheet.readiness_tier === 'Ready' && "bg-intel-green-dim/15 text-intel-green border-intel-green/30",
                          chargesheet.readiness_tier !== 'Ready' && "bg-intel-amber-dim/15 text-intel-amber border-intel-amber/30 animate-pulse"
                        )}>
                          {chargesheet.readiness_tier || 'Ready'}
                        </span>
                      </div>

                      <div className="space-y-1.5 pt-2 border-t border-border-subtle/50">
                        <span className="text-[9px] font-mono font-bold text-text-secondary uppercase">Overall Chargesheet Readiness</span>
                        <ConfidenceBar value={chargesheet.overall_readiness_score || 85} showLabel />
                      </div>

                      <div className="grid grid-cols-2 gap-4 pt-3 border-t border-border-subtle/50 font-mono text-[9px]">
                        <div className="space-y-0.5">
                          <span className="text-text-secondary uppercase text-[8px]">Procedural Compliance</span>
                          <p className="text-xs font-bold text-text-primary">{chargesheet.procedural_compliance_percentage || 0}%</p>
                        </div>
                        <div className="space-y-0.5">
                          <span className="text-text-secondary uppercase text-[8px]">Element Support</span>
                          <p className="text-xs font-bold text-text-primary">{chargesheet.element_readiness_percentage || 0}%</p>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="py-12">
                    <EmptyState 
                      title="No reports generated" 
                      description="Click the button to evaluate the case files and generate chargesheet readiness."
                      icon={FileSignature}
                    />
                  </div>
                )
              )}
            </div>
          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle className="w-[1px] hover:w-[3px] bg-border hover:bg-intel-blue transition-all duration-150 relative cursor-col-resize h-full" />

          {/* Right Panel: Procedural Checklists / Unsupported allegations */}
          <Panel id="cp-right" defaultSize={panelSizes['court-prep']?.[1] || 50} minSize={35} className="h-full flex flex-col overflow-hidden bg-surface border-l border-border">
            <div className="p-3 border-b border-border bg-surface/40 flex items-center justify-between shrink-0 select-none text-[10px] font-mono font-bold text-text-secondary uppercase">
              <span>{activeSubTab === 'admissibility' ? 'Procedural Checklists' : 'Unsupported Allegations'}</span>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-thin">
              {activeSubTab === 'admissibility' ? (
                !readiness || !readiness.checklist || readiness.checklist.length === 0 ? (
                  <div className="text-center py-8 text-text-muted font-mono text-[9px]">
                    No compliance checklist active. Run stress simulation first.
                  </div>
                ) : (
                  readiness.checklist.map((item: any, idx: number) => {
                    const isPassed = item.passed || item.status === 'compliant';
                    return (
                      <div 
                        key={idx} 
                        onClick={() => handleSelectChecklist(item.requirement || item.item_name, isPassed)}
                        className="p-3 bg-base border border-border-subtle hover:border-border rounded flex justify-between items-center text-[10px] font-mono cursor-pointer transition-colors"
                      >
                        <span className="font-sans text-text-secondary truncate max-w-[200px]">{item.requirement || item.item_name}</span>
                        <span className={cn(
                          "px-1.5 rounded text-[8px] font-bold border shrink-0 ml-3",
                          isPassed ? "bg-intel-green-dim/15 text-intel-green border-intel-green/20" : "bg-intel-red-dim/15 text-intel-red border-intel-red/25 animate-pulse"
                        )}>
                          {isPassed ? "PASSED" : "FAILED"}
                        </span>
                      </div>
                    );
                  })
                )
              ) : (
                !chargesheet || !chargesheet.unsupported_allegations || chargesheet.unsupported_allegations.length === 0 ? (
                  <div className="text-center py-8 text-text-muted font-mono text-[9px]">
                    No unsupported allegations. All targets linked successfully.
                  </div>
                ) : (
                  chargesheet.unsupported_allegations.map((item: string, idx: number) => (
                    <div 
                      key={idx} 
                      onClick={() => handleSelectAllegation(item)}
                      className="p-3 bg-base border border-border-subtle hover:border-border rounded text-[10px] text-text-secondary leading-snug cursor-pointer transition-all"
                    >
                      {item}
                    </div>
                  ))
                )
              )}
            </div>
          </Panel>
        </PanelGroup>
      </div>

    </div>
  );
}
