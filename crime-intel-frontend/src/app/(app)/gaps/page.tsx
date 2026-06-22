'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { intelligenceApi, reasoningApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { 
  PageHeader, IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, IntelCardFooter,
  EmptyState
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { 
  HelpCircle, RefreshCw, Play, ShieldAlert, CheckCircle2, 
  Layers, ArrowRight, Hourglass, Trash2, Check, Loader2 
} from 'lucide-react';
import { cn } from '@/lib/utils';

export default function EvidenceGapsPage() {
  const queryClient = useQueryClient();
  const { activeCaseId } = useCaseStore();
  const [selectedGapId, setSelectedGapId] = useState<string | null>(null);
  
  // Resolution note state
  const [resolutionNote, setResolutionNote] = useState('');

  // Query: Get gaps list
  const { data: gaps = [], isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['evidence-gaps', activeCaseId],
    queryFn: () => reasoningApi.listEvidenceGaps(activeCaseId!),
    enabled: !!activeCaseId,
  });

  // Mutation: Trigger gap scan
  const scanMutation = useMutation({
    mutationFn: () => intelligenceApi.runGapScan(activeCaseId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evidence-gaps', activeCaseId] });
      queryClient.invalidateQueries({ queryKey: ['graph-summary', activeCaseId] });
    }
  });

  // Mutation: Resolve gap
  const resolveMutation = useMutation({
    mutationFn: (data: { gapId: string; note: string }) => 
      intelligenceApi.resolveEvidenceGap(activeCaseId!, data.gapId, data.note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evidence-gaps', activeCaseId] });
      setSelectedGapId(null);
      setResolutionNote('');
    }
  });

  const handleResolve = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedGapId) return;
    resolveMutation.mutate({ gapId: selectedGapId, note: resolutionNote });
  };

  const selectedGap = gaps.find(g => g.id === selectedGapId);

  // Calculate stats
  const openGapsCount = gaps.filter(g => g.status === 'open').length;
  const resolvedGapsCount = gaps.filter(g => g.status === 'resolved').length;

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the evidence gap center."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Evidence Gap Center" 
        description="Identifies absent logical links (e.g., missing device owners), calculates investigative values, and tracks legal preservation deadlines."
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
              className="bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-xs gap-1.5 shadow-[0_0_15px_rgba(74,158,255,0.2)]"
            >
              {scanMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5" />
              )}
              <span>EXECUTE CRITICAL GAP ANALYSIS SCAN</span>
            </Button>
          </div>
        }
      />

      {/* Summary strips */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-surface/50 border border-border-subtle rounded-xl p-4 flex items-center justify-between">
          <span className="text-xs font-mono font-bold text-text-secondary uppercase">Unresolved Critical Gaps</span>
          <span className="text-xl font-bold font-mono text-intel-amber">{openGapsCount}</span>
        </div>
        <div className="bg-surface/50 border border-border-subtle rounded-xl p-4 flex items-center justify-between">
          <span className="text-xs font-mono font-bold text-text-secondary uppercase">Resolved Targets</span>
          <span className="text-xl font-bold font-mono text-intel-green">{resolvedGapsCount}</span>
        </div>
      </div>

      {/* Main split */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        
        {/* Left Side: List */}
        <div className="lg:col-span-5 space-y-4">
          <h3 className="text-xs font-mono font-bold text-text-secondary uppercase tracking-wider select-none">
            Evidence Gaps Registry ({gaps.length})
          </h3>

          <div className="space-y-2.5 max-h-[500px] overflow-y-auto pr-1">
            {isLoading ? (
              <div className="space-y-2">
                {[1, 2].map((_, i) => (
                  <div key={i} className="h-16 rounded-lg bg-surface animate-pulse" />
                ))}
              </div>
            ) : gaps.length === 0 ? (
              <EmptyState 
                title="All targets resolved" 
                description="Logical verify checks are complete. No active gaps identified."
                icon={CheckCircle2}
              />
            ) : (
              gaps.map((g) => {
                const isSelected = g.id === selectedGapId;
                const isOpen = g.status === 'open';
                return (
                  <div
                    key={g.id}
                    onClick={() => setSelectedGapId(g.id)}
                    className={cn(
                      "p-3.5 rounded-xl border transition-all duration-200 cursor-pointer flex justify-between items-center",
                      isSelected 
                        ? "bg-intel-blue-dim/10 border-intel-blue/50 shadow-md" 
                        : "bg-surface border-border-subtle hover:border-border/60"
                    )}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={cn(
                        "h-9 w-9 rounded-lg flex items-center justify-center shrink-0 border border-border-subtle",
                        isSelected ? "bg-intel-blue-dim/20 text-intel-blue" : "bg-elevated text-text-secondary"
                      )}>
                        <HelpCircle className="w-4.5 h-4.5" />
                      </div>
                      <div className="min-w-0 flex flex-col">
                        <span className="text-xs font-bold text-text-primary truncate font-sans">
                          {g.description}
                        </span>
                        <span className="text-[9px] font-mono text-text-muted mt-0.5 capitalize">
                          Urgency: {g.urgency} | Expected: {g.expected_value}
                        </span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1.5 shrink-0 ml-3">
                      <span className={cn(
                        "px-2 py-0.5 rounded text-[9px] font-mono font-bold border",
                        isOpen 
                          ? "bg-intel-amber-dim/15 text-intel-amber border-intel-amber/30 animate-pulse" 
                          : "bg-intel-green-dim/15 text-intel-green border-intel-green/30"
                      )}>
                        {g.status.toUpperCase()}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Side: Detail */}
        <div className="lg:col-span-7">
          {selectedGapId && selectedGap ? (
            <IntelCard glowColor={selectedGap.status === 'open' ? 'amber' : 'none'}>
              <IntelCardHeader>
                <div className="flex justify-between items-start gap-4">
                  <div>
                    <span className="text-[9px] font-mono font-bold text-intel-amber uppercase tracking-wider bg-intel-amber-dim/15 px-1.5 py-0.5 rounded border border-intel-amber/20">
                      Pending Logical Gap Target
                    </span>
                    <h3 className="text-base font-bold text-text-primary mt-2 leading-snug">
                      {selectedGap.description}
                    </h3>
                  </div>
                  <span className={cn(
                    "px-2.5 py-0.5 rounded-full text-xs font-mono font-bold border capitalize",
                    selectedGap.status === 'open' ? "bg-intel-amber-dim/15 text-intel-amber border-intel-amber/30 animate-pulse" : "bg-intel-green-dim/15 text-intel-green border-intel-green/30"
                  )}>
                    {selectedGap.status}
                  </span>
                </div>
              </IntelCardHeader>

              <IntelCardContent className="space-y-6">
                
                {/* Meta details */}
                <div className="grid grid-cols-2 gap-4 bg-base/50 p-4 rounded-lg border border-border-subtle">
                  <div className="space-y-1">
                    <span className="text-[9px] font-mono font-bold text-text-secondary uppercase">Expected value</span>
                    <p className="text-xs font-mono font-bold text-text-primary capitalize">{selectedGap.expected_value}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[9px] font-mono font-bold text-text-secondary uppercase">Urgency level</span>
                    <p className="text-xs font-mono font-bold text-text-primary capitalize">{selectedGap.urgency}</p>
                  </div>
                </div>

                {/* Narrative details */}
                <div className="space-y-2">
                  <h4 className="text-[10px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                    Gap Analysis Description
                  </h4>
                  <p className="text-xs font-sans text-text-secondary leading-relaxed bg-base/20 p-4 rounded-lg border border-border-subtle">
                    {selectedGap.narrative || "The system flagged this missing predicate. Adding evidence validating this link will resolve this node in the Neo4j cluster."}
                  </p>
                </div>

                {/* Action forms for unresolved */}
                {selectedGap.status === 'open' ? (
                  <form onSubmit={handleResolve} className="space-y-4 border-t border-border-subtle/50 pt-4">
                    <h4 className="text-[10px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                      Resolve Evidence Gap
                    </h4>
                    <div className="space-y-2">
                      <textarea
                        value={resolutionNote}
                        onChange={(e) => setResolutionNote(e.target.value)}
                        className="w-full h-20 bg-base border border-border rounded-lg px-3 py-2 text-xs font-sans text-text-primary focus:outline-none focus:border-intel-blue/60 resize-none"
                        placeholder="Provide details on how this gap was resolved (e.g. artifact hash uploaded)..."
                        required
                      />
                      <Button 
                        type="submit" 
                        className="w-full bg-intel-green hover:bg-intel-green/80 text-obsidian font-mono font-bold text-xs py-2 rounded-lg"
                        disabled={resolveMutation.isPending}
                      >
                        {resolveMutation.isPending ? "UPDATING LEDGER..." : "RESOLVE AND VALIDATE TARGET"}
                      </Button>
                    </div>
                  </form>
                ) : (
                  <div className="bg-intel-green-dim/10 border border-intel-green/20 p-4 rounded-xl space-y-2">
                    <div className="flex items-center gap-2 text-intel-green">
                      <CheckCircle2 className="w-4.5 h-4.5" />
                      <span className="text-xs font-bold uppercase tracking-wider">Resolution Cleared</span>
                    </div>
                    <p className="text-xs text-text-secondary leading-relaxed">
                      This gap was closed successfully with notes. Validated by cryptographic model ledger checks.
                    </p>
                  </div>
                )}

              </IntelCardContent>
            </IntelCard>
          ) : (
            <EmptyState 
              title="No gap selected" 
              description="Click on any evidence gap in the registry list on the left to view resolution parameters."
              icon={HelpCircle}
            />
          )}
        </div>

      </div>
    </div>
  );
}
