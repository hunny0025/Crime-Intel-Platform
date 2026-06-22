'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { graphApi, reasoningApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { useSelectionStore } from '@/lib/store/selection.store';
import { 
  IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent,
  EmptyState, TimelineDot, EntityChip, ConfidenceBar
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { 
  Clock, Filter, RefreshCw, Calendar, ArrowRight, Play, Pause, 
  FileText, ChevronRight, Activity, ShieldAlert, Sparkles, Loader2, GitPullRequest
} from 'lucide-react';
import { cn } from '@/lib/utils';

export default function TimelinePage() {
  const queryClient = useQueryClient();
  const { activeCaseId } = useCaseStore();
  const { panelSizes, setPanelSizes } = useWorkspaceStore();
  const { select } = useSelectionStore();

  const [fromDate, setFromDate] = useState('2026-01-01T00:00:00Z');
  const [toDate, setToDate] = useState('2026-12-31T23:59:59Z');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [counterfactualTargetId, setCounterfactualTargetId] = useState<string | null>(null);

  // Query: Get timeline events
  const { data: events = [], isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['timeline', activeCaseId, fromDate, toDate],
    queryFn: () => graphApi.getTimeline(activeCaseId!, fromDate, toDate),
    enabled: !!activeCaseId,
  });

  // Query: Get causal chain for selected event
  const { data: causalChainData, isLoading: isLoadingCausal } = useQuery({
    queryKey: ['causal-chain', activeCaseId, selectedEventId],
    queryFn: () => reasoningApi.getCausalChain(activeCaseId!, selectedEventId!),
    enabled: !!activeCaseId && !!selectedEventId,
  });

  // Mutation: Run counterfactual simulation
  const counterfactualMutation = useMutation({
    mutationFn: (body: { focal_event_id: string; removed_event_id: string }) =>
      reasoningApi.counterfactualSimulation(activeCaseId!, body),
  });

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the forensic timeline."
      />
    );
  }

  // Filter events based on search term
  const filteredEvents = events.filter(item => {
    if (!searchTerm) return true;
    const desc = (item.event.description || item.event.narrative || '').toLowerCase();
    const type = (item.event.event_type || '').toLowerCase();
    return desc.includes(searchTerm.toLowerCase()) || type.includes(searchTerm.toLowerCase());
  });

  const selectedEventItem = events.find(item => item.event.id === selectedEventId);

  const handleSelectEvent = (eventId: string) => {
    setSelectedEventId(eventId);
    setCounterfactualTargetId(null);
    counterfactualMutation.reset();
    
    const item = events.find(i => i.event.id === eventId);
    if (item) {
      select({
        id: item.event.id,
        type: 'event',
        name: item.event.description || item.event.narrative || item.event.event_type,
        metadata: {
          event_type: item.event.event_type,
          valid_from: item.event.valid_from,
          confidence: item.event.confidence
        }
      });
    }
  };

  const handleSelectEntity = (ent: any) => {
    select({
      id: ent.id,
      type: (ent.label?.toLowerCase() || 'custom') as any,
      name: ent.display_name || ent.name || ent.device_type || ent.address || ent.id.slice(0, 8),
      metadata: { ...ent }
    });
  };

  const runCounterfactual = (predId: string) => {
    if (!selectedEventId) return;
    setCounterfactualTargetId(predId);
    counterfactualMutation.mutate({
      focal_event_id: selectedEventId,
      removed_event_id: predId
    });
  };

  // Safe split layout check
  const sizes = panelSizes['timeline']?.length === 2 ? panelSizes['timeline'] : [65, 35];

  return (
    <div className="h-full w-full flex flex-col overflow-hidden bg-base">
      
      {/* 1. HEADER FILTERS BAR */}
      <div className="h-11 border-b border-border bg-surface px-4 flex items-center justify-between shrink-0 select-none text-[10px] font-mono">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <Clock className="w-3.5 h-3.5 text-intel-blue shrink-0" />
          <span className="font-bold text-text-primary uppercase shrink-0">Temporal Audit:</span>
          
          <div className="flex items-center gap-2 max-w-md w-full">
            <input 
              type="text" 
              placeholder="Search timeline events..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-base border border-border rounded px-2 py-1 text-[9px] text-text-primary focus:outline-none focus:border-intel-blue/50 font-sans"
            />
          </div>

          <div className="flex items-center gap-1.5 text-text-muted shrink-0 text-[9px]">
            <span>From:</span>
            <input
              type="text"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="bg-base border border-border-subtle rounded px-1.5 py-0.5 text-[8.5px] text-text-secondary focus:outline-none w-32"
            />
            <span>To:</span>
            <input
              type="text"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="bg-base border border-border-subtle rounded px-1.5 py-0.5 text-[8.5px] text-text-secondary focus:outline-none w-32"
            />
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 ml-3">
          <Button 
            variant="secondary"
            onClick={() => refetch()}
            disabled={isLoading || isRefetching}
            className="h-6 px-2.5 font-mono text-[9px] border-border-subtle"
          >
            <RefreshCw className={isRefetching ? "w-3 h-3 animate-spin" : "w-3 h-3"} />
          </Button>
        </div>
      </div>

      {/* 2. SPLIT LAYOUT */}
      <div className="flex-1 min-h-0 w-full relative">
        <PanelGroup 
          orientation="horizontal" 
          onLayoutChanged={(layout) => setPanelSizes('timeline', Object.values(layout))}
        >
          {/* Left Panel: Vertical Timeline List */}
          <Panel id="tl-left" defaultSize={sizes[0]} minSize={30} className="h-full flex flex-col overflow-hidden bg-base">
            <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
              {isLoading ? (
                <div className="space-y-4">
                  {[1, 2, 3].map((_, i) => (
                    <div key={i} className="h-16 rounded bg-surface animate-pulse" />
                  ))}
                </div>
              ) : filteredEvents.length === 0 ? (
                <EmptyState 
                  title="No timeline events" 
                  description="No events match your criteria or time range specifications."
                  icon={Clock}
                />
              ) : (
                <div className="relative border-l border-border-subtle/70 ml-28 pl-6 space-y-4 py-2">
                  {filteredEvents.map((item) => {
                    const evNode = item.event;
                    const isSelected = evNode.id === selectedEventId;
                    
                    return (
                      <div 
                        key={evNode.id} 
                        className="relative flex flex-col md:flex-row md:items-start cursor-pointer group"
                        onClick={() => handleSelectEvent(evNode.id)}
                      >
                        {/* Timestamp left position */}
                        <div className="absolute -left-[136px] w-28 text-right pr-6 font-mono text-[9.5px] text-text-secondary">
                          {evNode.valid_from ? new Date(evNode.valid_from).toLocaleDateString() : 'N/A'}
                          <div className="text-[8px] text-text-muted mt-0.5">
                            {evNode.valid_from ? new Date(evNode.valid_from).toLocaleTimeString() : ''}
                          </div>
                        </div>

                        {/* Chronological bullet marker */}
                        <div className="absolute -left-[32.5px] top-1">
                          <TimelineDot 
                            status={
                              evNode.confidence && evNode.confidence >= 0.7 
                                ? "compliant" 
                                : evNode.confidence && evNode.confidence >= 0.4 
                                  ? "due_soon" 
                                  : "general"
                            } 
                            size="sm" 
                          />
                        </div>

                        {/* Timeline Event details card */}
                        <div className={cn(
                          "flex-1 bg-surface border rounded p-3 transition-all duration-150",
                          isSelected 
                            ? "border-intel-blue bg-intel-blue-dim/5 shadow-[0_0_8px_rgba(74,158,255,0.05)]" 
                            : "border-border-subtle hover:border-border"
                        )}>
                          <div className="flex justify-between items-start mb-1 gap-4 font-mono text-[9.5px]">
                            <div>
                              <span className="text-[8px] font-bold text-intel-amber uppercase tracking-wider bg-intel-amber-dim/15 px-1 py-0.2 rounded border border-intel-amber/20">
                                {evNode.event_type || 'Forensic Event'}
                              </span>
                              <h4 className="text-xs font-bold text-text-primary mt-1.5 font-sans leading-tight">
                                {evNode.description || evNode.narrative || `Event Reference #${evNode.id.slice(0, 8)}`}
                              </h4>
                            </div>
                            {evNode.confidence !== undefined && (
                              <span className="text-[9px] font-bold text-intel-green bg-intel-green-dim/15 border border-intel-green/15 px-1.5 py-0.2 rounded shrink-0">
                                {Math.round(evNode.confidence * 100)}%
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle className="w-[1px] hover:w-[3px] bg-border hover:bg-intel-blue transition-all duration-150 relative cursor-col-resize h-full" />

          {/* Right Panel: Detail Inspector & Causal Reasoning */}
          <Panel id="tl-right" defaultSize={sizes[1]} minSize={25} className="h-full flex flex-col overflow-hidden bg-surface border-l border-border">
            {selectedEventId && selectedEventItem ? (
              <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
                
                {/* Header */}
                <div className="border-b border-border pb-3">
                  <span className="text-[8px] font-mono font-bold text-intel-amber uppercase tracking-wider bg-intel-amber-dim/15 px-1.5 py-0.5 rounded border border-intel-amber/20 inline-block mb-2">
                    {selectedEventItem.event.event_type}
                  </span>
                  <h3 className="text-sm font-bold text-text-primary leading-snug">
                    {selectedEventItem.event.description || selectedEventItem.event.narrative}
                  </h3>
                  <div className="text-[8px] font-mono text-text-muted mt-1.5 select-all">
                    ID: {selectedEventItem.event.id}
                  </div>
                </div>

                {/* Timing & Confidence */}
                <div className="grid grid-cols-2 gap-2 bg-base/40 p-2.5 border border-border-subtle rounded text-[9px] font-mono">
                  <div className="space-y-0.5">
                    <span className="text-[8px] text-text-secondary uppercase">Event Timestamp</span>
                    <p className="font-bold text-text-primary">
                      {selectedEventItem.event.valid_from ? new Date(selectedEventItem.event.valid_from).toLocaleString() : 'N/A'}
                    </p>
                  </div>
                  <div className="space-y-0.5">
                    <span className="text-[8px] text-text-secondary uppercase">Confidence Coefficient</span>
                    <div>
                      <ConfidenceBar value={(selectedEventItem.event.confidence || 0.8) * 100} showLabel />
                    </div>
                  </div>
                </div>

                {/* Causal Chain Section */}
                <div className="space-y-2.5">
                  <div className="flex items-center gap-1 text-[9px] font-mono font-bold text-text-secondary uppercase">
                    <GitPullRequest className="w-3.5 h-3.5 text-intel-blue" />
                    <span>Causal Chain Traversal</span>
                  </div>

                  {isLoadingCausal ? (
                    <div className="flex py-3 justify-center">
                      <Loader2 className="w-4 h-4 animate-spin text-intel-blue" />
                    </div>
                  ) : !causalChainData || (!causalChainData.chains?.length && !causalChainData.immediate_causes?.length) ? (
                    <div className="p-3 bg-base/30 border border-border-subtle rounded text-[9px] font-mono text-text-muted text-center leading-normal">
                      No direct CAUSED links registered for this event. 
                      Use Graph Explorer to connect causal sequences.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {causalChainData.chains?.map((chain: any, cIdx: number) => (
                        <div key={cIdx} className="p-2.5 bg-base border border-border-subtle rounded space-y-2">
                          <div className="flex justify-between items-center text-[8px] font-mono border-b border-border-subtle/50 pb-1.5">
                            <span className="font-bold text-intel-purple">CAUSAL PATH #{cIdx + 1}</span>
                            <span className="text-text-muted">Chain Conf: {Math.round(chain.chain_confidence * 100)}%</span>
                          </div>

                          <div className="relative border-l border-intel-blue/40 ml-2 pl-3.5 space-y-2 font-mono text-[9px]">
                            {chain.events.map((evt: any, eIdx: number) => {
                              const isFocal = evt.id === selectedEventId;
                              const link = chain.links[eIdx - 1]; // Predecessor link
                              return (
                                <div key={evt.id} className="relative">
                                  <div className={cn(
                                    "absolute -left-[19.5px] top-1 h-1.5 w-1.5 rounded-full border border-obsidian",
                                    isFocal ? "bg-intel-blue animate-ping" : "bg-text-secondary"
                                  )} />
                                  <div className="flex flex-col">
                                    <div className="flex items-center justify-between">
                                      <span className={cn(
                                        "font-bold truncate max-w-[150px]",
                                        isFocal ? "text-intel-blue font-bold" : "text-text-primary"
                                      )}>
                                        {evt.display}
                                      </span>
                                      {!isFocal && (
                                        <button
                                          onClick={() => runCounterfactual(evt.id)}
                                          disabled={counterfactualMutation.isPending}
                                          className="text-[7.5px] font-bold text-intel-amber hover:text-intel-amber/80 border border-intel-amber/20 bg-intel-amber-dim/5 px-1 py-0.2 rounded"
                                        >
                                          SIMULATE ABSENCE
                                        </button>
                                      )}
                                    </div>
                                    {link && (
                                      <span className="text-[8px] text-text-muted italic leading-none mt-0.5">
                                        ↳ caused by {link.mechanism} ({Math.round(link.confidence * 100)}% conf)
                                      </span>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ))}

                      {/* Display Counterfactual Result */}
                      {counterfactualMutation.isPending && (
                        <div className="p-2.5 bg-obsidian border border-border-subtle rounded flex items-center justify-center gap-2">
                          <Loader2 className="w-3.5 h-3.5 animate-spin text-intel-amber" />
                          <span className="font-mono text-[9px] text-text-secondary">Simulating alternate reality timelines...</span>
                        </div>
                      )}

                      {counterfactualMutation.data && (
                        <div className={cn(
                          "p-2.5 border rounded font-mono text-[9px] space-y-1.5 animate-in fade-in duration-200",
                          counterfactualMutation.data.counterfactual_result === 'focal_event_prevented'
                            ? "bg-intel-red-dim/10 border-intel-red/35"
                            : "bg-intel-green-dim/10 border-intel-green/35"
                        )}>
                          <div className="flex justify-between items-center text-[8.5px] font-bold">
                            <span className="flex items-center gap-1">
                              <ShieldAlert className="w-3.5 h-3.5" />
                              <span>COUNTERFACTUAL ANALYSIS COMPLETE</span>
                            </span>
                            <span className="uppercase text-[8px] px-1 py-0.2 rounded border bg-obsidian">
                              {counterfactualMutation.data.counterfactual_result === 'focal_event_prevented' ? 'CRITICAL LINK' : 'REDUNDANT PATH'}
                            </span>
                          </div>
                          <p className="text-text-secondary leading-snug text-[9.5px]">
                            {counterfactualMutation.data.reasoning}
                          </p>
                          <div className="text-[8px] text-text-muted flex justify-between pt-1 border-t border-border-subtle/30">
                            <span>Effect: {counterfactualMutation.data.counterfactual_result.replace('_', ' ')}</span>
                            <span>Simulation confidence: {Math.round(counterfactualMutation.data.confidence * 100)}%</span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Connected Entities */}
                <div className="space-y-2">
                  <h4 className="text-[9px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                    Associated Entities
                  </h4>
                  {selectedEventItem.connected_entities && selectedEventItem.connected_entities.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5 bg-base/20 p-2.5 border border-border-subtle rounded">
                      {selectedEventItem.connected_entities.map((ent, idx) => (
                        <div 
                          key={idx}
                          onClick={() => handleSelectEntity(ent)}
                          className="cursor-pointer"
                        >
                          <EntityChip 
                            type={ent.label as any}
                            label={ent.display_name || ent.name || ent.device_type || ent.address || ent.id.slice(0, 8)}
                            clickable
                          />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[9px] font-mono text-text-muted bg-base/10 p-2 border border-border-subtle border-dashed rounded text-center">
                      No entities bound to this event card.
                    </div>
                  )}
                </div>

                {/* Evidence Basis */}
                <div className="space-y-2">
                  <h4 className="text-[9px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                    Evidentiary Validation Basis
                  </h4>
                  {selectedEventItem.evidence_basis && selectedEventItem.evidence_basis.length > 0 ? (
                    <div className="space-y-1.5 font-mono text-[9px]">
                      {selectedEventItem.evidence_basis.map((basis, idx) => (
                        <div 
                          key={idx}
                          onClick={() => select({ id: basis, type: 'evidence', name: basis })}
                          className="p-2 bg-base border border-border-subtle rounded flex items-center gap-2 cursor-pointer hover:border-border"
                        >
                          <FileText className="w-3.5 h-3.5 text-intel-blue shrink-0" />
                          <span className="text-text-secondary truncate text-[9.5px] font-sans">{basis}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[9px] font-mono text-text-muted bg-base/10 p-2 border border-border-subtle border-dashed rounded text-center">
                      No source files mapped as structural evidence basis.
                    </div>
                  )}
                </div>

              </div>
            ) : (
              <EmptyState 
                title="No event selected" 
                description="Select any chronological event from the timeline stream on the left to inspect its structural metadata, connected entities, and trace its causal chain."
                icon={GitPullRequest}
              />
            )}
          </Panel>
        </PanelGroup>
      </div>

    </div>
  );
}
