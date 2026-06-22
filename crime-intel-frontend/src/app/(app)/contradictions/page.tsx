'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { intelligenceApi, reasoningApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { 
  PageHeader, IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, IntelCardFooter,
  EmptyState, SeverityIndicator 
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { 
  AlertOctagon, RefreshCw, Play, ShieldAlert, CheckCircle2, 
  Layers, ChevronRight, HelpCircle, Loader2 
} from 'lucide-react';
import { cn } from '@/lib/utils';

export default function ContradictionsPage() {
  const queryClient = useQueryClient();
  const { activeCaseId } = useCaseStore();
  const [selectedContradictionId, setSelectedContradictionId] = useState<string | null>(null);

  // Query: Get contradictions list
  const { data: contradictions = [], isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['contradictions', activeCaseId],
    queryFn: () => reasoningApi.listContradictions(activeCaseId!),
    enabled: !!activeCaseId,
  });

  // Mutation: Trigger contradiction scan
  const scanMutation = useMutation({
    mutationFn: () => intelligenceApi.runContradictionScan(activeCaseId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contradictions', activeCaseId] });
      queryClient.invalidateQueries({ queryKey: ['graph-summary', activeCaseId] });
    }
  });

  const selectedContradiction = contradictions.find(c => c.id === selectedContradictionId);

  // Calculate counts
  const highSeverityCount = contradictions.filter(c => c.severity === 'high').length;
  const medSeverityCount = contradictions.filter(c => c.severity === 'medium').length;
  const lowSeverityCount = contradictions.filter(c => c.severity === 'low').length;

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the contradiction monitor."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Contradiction Monitor" 
        description="Scans evidence nodes, identifies logical predicates inconsistencies, and triggers warnings for conflicting testimonies."
        actions={
          <div className="flex gap-2">
            <Button 
              variant="secondary"
              onClick={() => refetch()}
              disabled={isLoading || isRefetching}
              className="font-mono text-xs border-border-subtle"
            >
              <RefreshCw className={isRefetching ? "w-3.5 h-3.5 animate-spin" : "w-3.5 h-3.5"} />
            </Button>
            <Button 
              onClick={() => scanMutation.mutate()}
              disabled={scanMutation.isPending}
              className="bg-intel-red hover:bg-intel-red/80 text-text-primary font-mono font-bold text-xs gap-1.5 shadow-[0_0_15px_rgba(244,63,94,0.2)]"
            >
              {scanMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5" />
              )}
              <span>RUN LOGICAL CONTRADICTION SCAN</span>
            </Button>
          </div>
        }
      />

      {/* Severity counter bar */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-surface/50 border border-border-subtle rounded-xl p-4 flex items-center justify-between">
          <span className="text-xs font-mono font-bold text-text-secondary uppercase">High Severity Warnings</span>
          <span className="text-xl font-bold font-mono text-intel-red">{highSeverityCount}</span>
        </div>
        <div className="bg-surface/50 border border-border-subtle rounded-xl p-4 flex items-center justify-between">
          <span className="text-xs font-mono font-bold text-text-secondary uppercase">Medium Warnings</span>
          <span className="text-xl font-bold font-mono text-intel-amber">{medSeverityCount}</span>
        </div>
        <div className="bg-surface/50 border border-border-subtle rounded-xl p-4 flex items-center justify-between">
          <span className="text-xs font-mono font-bold text-text-secondary uppercase">Low Warnings</span>
          <span className="text-xl font-bold font-mono text-intel-blue">{lowSeverityCount}</span>
        </div>
      </div>

      {/* Main split */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        
        {/* Left Side: List */}
        <div className="lg:col-span-5 space-y-4">
          <h3 className="text-xs font-mono font-bold text-text-secondary uppercase tracking-wider select-none">
            Inconsistencies Registry ({contradictions.length})
          </h3>

          <div className="space-y-2.5 max-h-[500px] overflow-y-auto pr-1">
            {isLoading ? (
              <div className="space-y-2">
                {[1, 2].map((_, i) => (
                  <div key={i} className="h-16 rounded-lg bg-surface animate-pulse" />
                ))}
              </div>
            ) : contradictions.length === 0 ? (
              <EmptyState 
                title="No active contradictions" 
                description="Logical verify checks are clean. Trigger a new scan if you recently added evidence artifacts."
                icon={CheckCircle2}
              />
            ) : (
              contradictions.map((c) => {
                const isSelected = c.id === selectedContradictionId;
                return (
                  <div
                    key={c.id}
                    onClick={() => setSelectedContradictionId(c.id)}
                    className={cn(
                      "p-3.5 rounded-xl border transition-all duration-200 cursor-pointer flex justify-between items-center",
                      isSelected 
                        ? "bg-intel-red-dim/10 border-intel-red/50 shadow-md" 
                        : "bg-surface border-border-subtle hover:border-border/60"
                    )}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={cn(
                        "h-9 w-9 rounded-lg flex items-center justify-center shrink-0 border border-border-subtle",
                        isSelected ? "bg-intel-red-dim/20 text-intel-red" : "bg-elevated text-text-secondary"
                      )}>
                        <AlertOctagon className="w-4.5 h-4.5" />
                      </div>
                      <div className="min-w-0 flex flex-col">
                        <span className="text-xs font-bold text-text-primary truncate font-sans">
                          {c.description}
                        </span>
                        <span className="text-[9px] font-mono text-text-muted truncate mt-0.5">
                          Type: {c.contradiction_type}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1.5 shrink-0 ml-3">
                      <SeverityIndicator severity={c.severity} showIcon={false} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Side: Detail */}
        <div className="lg:col-span-7">
          {selectedContradictionId && selectedContradiction ? (
            <IntelCard glowColor={selectedContradiction.severity === 'high' ? 'red' : 'none'}>
              <IntelCardHeader>
                <div className="flex justify-between items-start gap-4">
                  <div>
                    <span className="text-[9px] font-mono font-bold text-intel-red uppercase tracking-wider bg-intel-red-dim/15 px-1.5 py-0.5 rounded border border-intel-red/20">
                      Logical Inconsistency Detected
                    </span>
                    <h3 className="text-base font-bold text-text-primary mt-2 leading-snug">
                      {selectedContradiction.description}
                    </h3>
                  </div>
                  <SeverityIndicator severity={selectedContradiction.severity} />
                </div>
              </IntelCardHeader>

              <IntelCardContent className="space-y-6">
                
                {/* Information matrix */}
                <div className="grid grid-cols-2 gap-4 bg-base/50 p-4 rounded-lg border border-border-subtle">
                  <div className="space-y-1">
                    <span className="text-[9px] font-mono font-bold text-text-secondary uppercase">Scanned Category</span>
                    <p className="text-xs font-mono font-bold text-text-primary capitalize">{selectedContradiction.contradiction_type}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[9px] font-mono font-bold text-text-secondary uppercase">Log Detection Time</span>
                    <p className="text-xs font-mono font-bold text-text-primary">
                      {selectedContradiction.detected_at ? new Date(selectedContradiction.detected_at).toLocaleString() : 'N/A'}
                    </p>
                  </div>
                </div>

                {/* Explanation text */}
                <div className="space-y-2">
                  <h4 className="text-[10px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                    Inconsistency Analysis
                  </h4>
                  <p className="text-xs font-sans text-text-secondary leading-relaxed bg-base/20 p-4 rounded-lg border border-border-subtle">
                    {selectedContradiction.narrative || "The system flagged this entry due to conflicting timestamps or overlapping identity constraints across testimonies in the Neo4j timeline. Action is recommended to confirm or reject mapping credentials."}
                  </p>
                </div>

                {/* Involved entities */}
                {selectedContradiction.involved_entities && selectedContradiction.involved_entities.length > 0 && (
                  <div className="space-y-3">
                    <h4 className="text-[10px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                      Involved Graph Elements
                    </h4>
                    <div className="space-y-2">
                      {selectedContradiction.involved_entities.map((node: any, idx: number) => (
                        <div key={idx} className="flex justify-between items-center p-3 bg-base/30 border border-border-subtle rounded-lg">
                          <div className="flex items-center gap-2">
                            <Layers className="w-3.5 h-3.5 text-text-secondary" />
                            <span className="text-xs font-bold text-text-primary">{node.display_name || node.id.slice(0, 8)}</span>
                          </div>
                          <span className="text-[9px] font-mono text-text-muted capitalize">{node.label}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

              </IntelCardContent>
            </IntelCard>
          ) : (
            <EmptyState 
              title="No warning selected" 
              description="Click on any logic warning in the registry list on the left to view the conflicting entities and reasoning narratives."
              icon={AlertOctagon}
            />
          )}
        </div>

      </div>
    </div>
  );
}
