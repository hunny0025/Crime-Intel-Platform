'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { legalApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { useSelectionStore } from '@/lib/store/selection.store';
import { 
  IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, 
  EmptyState 
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { Scale, Play, RefreshCw, CheckCircle2, ShieldAlert, Check, X, Loader2, CheckSquare } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function LegalConsoleWorkspace() {
  const queryClient = useQueryClient();
  const { activeCaseId } = useCaseStore();
  const { panelSizes, setPanelSizes } = useWorkspaceStore();
  const { select } = useSelectionStore();
  const [selectedMappingId, setSelectedMappingId] = useState<string | null>(null);

  // Queries
  const { data: elementMap, isLoading: isLoadingMap, refetch: refetchMap, isRefetching: isRefetchingMap } = useQuery({
    queryKey: ['element-map', activeCaseId],
    queryFn: () => legalApi.getElementMap(activeCaseId!),
    enabled: !!activeCaseId,
  });

  const { data: complianceReport, isLoading: isLoadingCompliance, refetch: refetchCompliance } = useQuery({
    queryKey: ['compliance-report', activeCaseId],
    queryFn: () => legalApi.getComplianceReport(activeCaseId!),
    enabled: !!activeCaseId,
  });

  // Mutations
  const mapMutation = useMutation({
    mutationFn: () => legalApi.mapElements(activeCaseId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['element-map', activeCaseId] });
    }
  });

  const confirmMutation = useMutation({
    mutationFn: (mappingId: string) => legalApi.confirmMapping(activeCaseId!, mappingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['element-map', activeCaseId] });
    }
  });

  const scanMutation = useMutation({
    mutationFn: () => legalApi.scanCompliance(activeCaseId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-report', activeCaseId] });
    }
  });

  const mappings = elementMap?.mappings || [];
  const alerts = complianceReport?.alerts || [];
  const selectedMapping = mappings.find((m: any) => m.id === selectedMappingId);

  // Sync selection store on item click
  const handleSelectMapping = (id: string) => {
    setSelectedMappingId(id);
    const m = mappings.find((item: any) => item.id === id);
    if (m) {
      select({
        id: m.id,
        type: 'legal',
        name: `Element: ${m.element_id}`,
        metadata: {
          confidence: m.confidence,
          status: m.status
        }
      });
    }
  };

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the legal elements mapping and compliance audits."
      />
    );
  }

  return (
    <div className="h-full w-full flex flex-col overflow-hidden bg-base">
      
      {/* 1. ACTIONS HEADER */}
      <div className="h-10 border-b border-border bg-surface px-4 flex items-center justify-between shrink-0 select-none text-[10px] font-mono">
        <div className="flex items-center gap-1.5 text-text-secondary">
          <Scale className="w-3.5 h-3.5 text-intel-purple" />
          <span>LEGAL ELEMENT MATRIX & COMPLIANCE</span>
        </div>

        <div className="flex items-center gap-2">
          <Button 
            variant="secondary"
            onClick={() => {
              refetchMap();
              refetchCompliance();
            }}
            className="h-6 px-2.5 font-mono text-[9px] border-border-subtle"
          >
            <RefreshCw className="w-3 h-3" />
          </Button>
          <Button 
            onClick={() => mapMutation.mutate()}
            disabled={mapMutation.isPending}
            className="h-6 px-3 bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-[9px] gap-1 shrink-0"
          >
            {mapMutation.isPending ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : "RUN INGREDIENT MAPPING"}
          </Button>
          <Button 
            onClick={() => scanMutation.mutate()}
            disabled={scanMutation.isPending}
            className="h-6 px-3 bg-intel-purple hover:bg-intel-purple/80 text-text-primary border border-intel-purple/30 font-mono font-bold text-[9px] gap-1 shrink-0"
          >
            {scanMutation.isPending ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : "RUN COMPLIANCE Scan"}
          </Button>
        </div>
      </div>

      {/* 2. SPLIT LAYOUT AREA */}
      <div className="flex-1 min-h-0 w-full relative">
        <PanelGroup 
          orientation="horizontal" 
          onLayoutChanged={(layout) => setPanelSizes('legal-console', Object.values(layout))}
        >
          {/* Left Panel: Legal Element Mapping Matrix */}
          <Panel id="lc-left" defaultSize={panelSizes['legal-console'][0]} minSize={30} className="h-full flex flex-col overflow-hidden bg-base">
            <div className="p-3 border-b border-border bg-surface/40 flex items-center justify-between shrink-0 select-none text-[10px] font-mono font-bold text-text-secondary uppercase">
              <span>Ingredient Mappings</span>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-thin">
              {isLoadingMap ? (
                <div className="space-y-2">
                  {[1, 2].map((_, i) => (
                    <div key={i} className="h-16 rounded bg-surface animate-pulse" />
                  ))}
                </div>
              ) : mappings.length === 0 ? (
                <div className="text-center py-8 text-text-muted font-mono text-[9px] border border-dashed border-border rounded bg-surface/5">
                  No elements mapped. Run Ingredient Mapping.
                </div>
              ) : (
                mappings.map((m: any) => {
                  const isSelected = m.id === selectedMappingId;
                  return (
                    <div
                      key={m.id}
                      onClick={() => handleSelectMapping(m.id)}
                      className={cn(
                        "p-3 rounded border transition-all duration-150 cursor-pointer flex flex-col gap-2",
                        isSelected 
                          ? "bg-intel-purple-dim/15 border-intel-purple/50 shadow-sm" 
                          : "bg-surface border-border-subtle hover:border-border/60"
                      )}
                    >
                      <div className="flex justify-between items-start gap-3 text-[10px] font-mono">
                        <span className="font-bold text-text-primary">Element: {m.element_id}</span>
                        <span className="text-intel-blue font-bold">Conf: {Math.round((m.confidence || 0.8) * 100)}%</span>
                      </div>
                      
                      <div className="flex justify-between items-center text-[8px] font-mono text-text-muted border-t border-border-subtle/30 pt-1.5 mt-0.5">
                        <span>Status: {m.status}</span>
                        <span className="truncate max-w-[150px]">Artifact: {m.artifact_id.slice(0, 8)}...</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle className="w-[1px] hover:w-[3px] bg-border hover:bg-intel-blue transition-all duration-150 relative cursor-col-resize h-full" />

          {/* Right Panel: Element Details & Bottom Compliance Alerts */}
          <Panel id="lc-right" defaultSize={panelSizes['legal-console'][1]} minSize={40} className="h-full flex flex-col overflow-hidden bg-surface border-l border-border">
            
            {/* Top Sub-Panel: Mapping Details */}
            <div className="flex-1 overflow-y-auto p-4 border-b border-border scrollbar-thin space-y-4">
              {selectedMappingId && selectedMapping ? (
                <div className="space-y-4">
                  <div className="flex justify-between items-start border-b border-border pb-3">
                    <div>
                      <span className="text-[8px] font-mono font-bold text-intel-purple uppercase tracking-wider bg-intel-purple-dim/15 px-1.5 py-0.5 rounded border border-intel-purple/25">
                        Legal Mapping Ingredient
                      </span>
                      <h3 className="text-xs font-bold text-text-primary mt-2 leading-snug font-mono">
                        Element ID: {selectedMapping.element_id}
                      </h3>
                    </div>
                    <button 
                      onClick={() => setSelectedMappingId(null)}
                      className="text-text-secondary hover:text-text-primary p-0.5"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <div className="bg-base/40 p-3 rounded border border-border-subtle space-y-2 text-[10px] font-mono">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[8px] text-text-secondary uppercase">Associated Artifact</span>
                      <span className="text-intel-blue font-bold break-all select-all">{selectedMapping.artifact_id}</span>
                    </div>
                    
                    <div className="flex justify-between items-center border-t border-border-subtle/50 pt-2">
                      <span className="text-[8px] text-text-secondary uppercase">Confidence Quotient</span>
                      <span className="text-text-primary font-bold">{Math.round((selectedMapping.confidence || 0.8) * 100)}%</span>
                    </div>
                    
                    <div className="flex justify-between items-center">
                      <span className="text-[8px] text-text-secondary uppercase">Approval status</span>
                      <span className="text-text-primary font-bold capitalize">{selectedMapping.status}</span>
                    </div>
                  </div>

                  {selectedMapping.status === 'pending' && (
                    <Button 
                      onClick={() => confirmMutation.mutate(selectedMapping.id)}
                      disabled={confirmMutation.isPending}
                      className="w-full bg-intel-green hover:bg-intel-green/80 text-obsidian font-mono font-bold text-[9px] h-8 flex items-center justify-center gap-1 shadow-md"
                    >
                      {confirmMutation.isPending ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <>
                          <Check className="w-3.5 h-3.5" />
                          <span>CONFIRM & SATISFY PROVISION ELEMENT</span>
                        </>
                      )}
                    </Button>
                  )}
                </div>
              ) : (
                <EmptyState 
                  title="No mapping selected" 
                  description="Select a legal mapping from the index list on the left to verify evidence satisfaction."
                  icon={Scale}
                />
              )}
            </div>

            {/* Bottom Sub-Panel: Compliance Alerts Stream */}
            <div className="h-44 flex flex-col overflow-hidden bg-base/60 shrink-0">
              <div className="p-2.5 border-b border-border bg-surface/80 flex items-center justify-between shrink-0 select-none text-[8px] font-mono font-bold text-text-secondary uppercase">
                <span>Procedural Compliance Alerts</span>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-thin">
                {isLoadingCompliance ? (
                  <div className="space-y-1.5">
                    <div className="h-10 bg-surface rounded animate-pulse" />
                  </div>
                ) : alerts.length === 0 ? (
                  <div className="text-center py-6 text-text-muted font-mono text-[9px]">
                    No compliance warnings or deadlines logged.
                  </div>
                ) : (
                  alerts.map((al: any) => (
                    <div 
                      key={al.id} 
                      className={cn(
                        "p-2.5 bg-surface border rounded flex justify-between items-center text-[9px] font-mono",
                        al.alert_severity === 'high' ? "border-intel-red/35" : "border-border-subtle"
                      )}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <CheckSquare className="w-3.5 h-3.5 text-intel-blue shrink-0" />
                        <div className="min-w-0 flex flex-col gap-0.2">
                          <span className="font-bold text-text-primary truncate">{al.milestone_name}</span>
                          <span className="text-[8px] text-text-muted">Req: {al.requirement_id}</span>
                        </div>
                      </div>
                      <span className={cn(
                        "px-1 rounded text-[7.5px] font-bold border shrink-0 ml-3",
                        al.status === 'compliant' && "bg-intel-green-dim/15 text-intel-green border-intel-green/20",
                        al.status === 'non_compliant' && "bg-intel-red-dim/15 text-intel-red border-intel-red/20",
                        al.status !== 'compliant' && al.status !== 'non_compliant' && "bg-intel-amber-dim/15 text-intel-amber border-intel-amber/35"
                      )}>
                        {al.status.toUpperCase()}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>

          </Panel>
        </PanelGroup>
      </div>

    </div>
  );
}
