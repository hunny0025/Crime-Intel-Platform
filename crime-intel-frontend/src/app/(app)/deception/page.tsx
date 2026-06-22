'use client';

import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deceptionApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { 
  PageHeader, IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, IntelCardFooter,
  EmptyState, ConfidenceBar 
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { Fingerprint, Play, ShieldAlert, Sparkles, Loader2 } from 'lucide-react';

export default function DeceptionPage() {
  const { activeCaseId } = useCaseStore();
  const [targetId, setTargetId] = useState('');
  const [targetType, setTargetType] = useState('evidence_artifact');

  const assessMutation = useMutation({
    mutationFn: (data: { artifact_id?: string; osint_record_id?: string }) => 
      deceptionApi.assessDeception(activeCaseId!, data),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload = targetType === 'evidence_artifact' 
      ? { artifact_id: targetId } 
      : { osint_record_id: targetId };
    assessMutation.mutate(payload);
  };

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the deception assessment page."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Cognitive Deception Assessor" 
        description="Run LLM deception inference evaluations on transcripts, testimony records, and OSINT content logs."
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left: Input Form */}
        <div className="lg:col-span-5">
          <IntelCard>
            <IntelCardHeader>
              <IntelCardTitle>
                <Fingerprint className="w-5 h-5 text-intel-red animate-pulse" />
                <span>Assess Target Deception</span>
              </IntelCardTitle>
            </IntelCardHeader>
            <form onSubmit={handleSubmit}>
              <IntelCardContent className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-secondary">
                    Target Type
                  </label>
                  <select
                    value={targetType}
                    onChange={(e) => setTargetType(e.target.value)}
                    className="w-full bg-base border border-border rounded-lg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-intel-blue/60"
                  >
                    <option value="evidence_artifact">Evidence Artifact UUID</option>
                    <option value="osint_record">OSINT Record ID</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-secondary">
                    Target Identifier UUID
                  </label>
                  <input
                    type="text"
                    value={targetId}
                    onChange={(e) => setTargetId(e.target.value)}
                    className="w-full bg-base border border-border rounded-lg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-intel-blue/60"
                    placeholder="Enter UUID..."
                    required
                  />
                </div>
              </IntelCardContent>
              <IntelCardFooter>
                <Button 
                  type="submit" 
                  className="w-full bg-intel-red hover:bg-intel-red/80 text-text-primary font-mono font-bold text-xs"
                  disabled={assessMutation.isPending}
                >
                  {assessMutation.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : "RUN COGNITIVE DECEPTION INFERENCE"}
                </Button>
              </IntelCardFooter>
            </form>
          </IntelCard>
        </div>

        {/* Right: Results */}
        <div className="lg:col-span-7">
          {assessMutation.data ? (
            <IntelCard glowColor={assessMutation.data.deception_score >= 0.6 ? 'red' : 'none'}>
              <IntelCardHeader className="flex flex-row justify-between items-start gap-4">
                <div>
                  <span className="text-[9px] font-mono font-bold text-intel-red uppercase tracking-wider bg-intel-red-dim/15 px-1.5 py-0.5 rounded border border-intel-red/20">
                    Deception Inference Score
                  </span>
                  <h3 className="text-xl font-mono font-bold text-text-primary mt-2">
                    Score: {Math.round(assessMutation.data.deception_score * 100)}%
                  </h3>
                </div>
                <div className="text-right">
                  <span className="text-[9px] font-mono text-text-muted">Inference Model</span>
                  <p className="text-xs font-mono font-bold text-text-secondary mt-0.5">{assessMutation.data.model_name}</p>
                </div>
              </IntelCardHeader>
              <IntelCardContent className="space-y-6">
                
                {/* Confidence */}
                <div className="space-y-2">
                  <span className="text-[10px] font-mono font-bold text-text-secondary uppercase">Inference Confidence</span>
                  <ConfidenceBar value={assessMutation.data.confidence} showLabel />
                </div>

                {/* Explanation */}
                <div className="space-y-2">
                  <h4 className="text-[10px] font-mono font-bold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
                    <ShieldAlert className="w-4 h-4 text-intel-red" />
                    <span>Deception Explanation Narrative</span>
                  </h4>
                  <p className="text-xs font-sans text-text-secondary leading-relaxed bg-base/20 p-4 rounded-lg border border-border-subtle">
                    {assessMutation.data.explanation}
                  </p>
                </div>

              </IntelCardContent>
            </IntelCard>
          ) : (
            <EmptyState 
              title="Deception details empty" 
              description="Enter a target UUID and run deception inference to compute suspicious scores."
              icon={Fingerprint}
            />
          )}
        </div>
      </div>
    </div>
  );
}
