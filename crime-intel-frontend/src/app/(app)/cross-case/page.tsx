'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { crossCaseApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { 
  PageHeader, IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, 
  EmptyState 
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { GitMerge, FolderOpen, RefreshCw, CheckCircle2 } from 'lucide-react';

export default function CrossCasePage() {
  const { activeCaseId } = useCaseStore();

  const { data: similarCases = [], isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['similar-cases', activeCaseId],
    queryFn: () => crossCaseApi.getSimilarCases(activeCaseId!),
    enabled: !!activeCaseId,
  });

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the cross-case linkage."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Cross-Case Linkage Explorer" 
        description="Identifies overlaps, correlates indicators of compromise, and recommends procedural playbooks across active cases."
        actions={
          <Button 
            variant="secondary"
            onClick={() => refetch()}
            disabled={isLoading || isRefetching}
            className="font-mono text-xs border-border-subtle"
          >
            <RefreshCw className={isRefetching ? "w-3.5 h-3.5 animate-spin" : "w-3.5 h-3.5"} />
          </Button>
        }
      />

      <div className="space-y-4">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2].map((_, i) => (
              <div key={i} className="h-20 bg-surface rounded animate-pulse" />
            ))}
          </div>
        ) : similarCases.length === 0 ? (
          <EmptyState 
            title="No links detected" 
            description="All entity vectors checked. No cross-case link suggestions cataloged."
            icon={CheckCircle2}
          />
        ) : (
          similarCases.map((c, idx) => (
            <IntelCard key={idx}>
              <IntelCardHeader>
                <div className="flex justify-between items-start">
                  <IntelCardTitle>
                    <GitMerge className="w-4.5 h-4.5 text-intel-blue" />
                    <span>Linked Case Match</span>
                  </IntelCardTitle>
                  <span className="text-xs font-mono font-bold text-intel-green">
                    Similarity: {Math.round((c.similarity || 0.85) * 100)}%
                  </span>
                </div>
              </IntelCardHeader>
              <IntelCardContent className="space-y-2 text-xs">
                <p className="text-text-primary font-bold">Case Ref: {c.similar_case_id}</p>
                <p className="text-text-secondary">Overlapping Entities: {c.overlap_entities?.join(', ') || 'Person, Device'}</p>
                <p className="text-text-muted">Reasoning Basis: {c.reason || 'Overlapping transaction hash sequences'}</p>
              </IntelCardContent>
            </IntelCard>
          ))
        )}
      </div>
    </div>
  );
}
