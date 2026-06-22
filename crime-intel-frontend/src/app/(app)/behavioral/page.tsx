'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { behavioralApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { 
  PageHeader, IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, IntelCardFooter,
  EmptyState, SeverityIndicator 
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { Activity, User, BarChart, ShieldAlert, Play, RefreshCw, Loader2 } from 'lucide-react';

export default function BehavioralPage() {
  const queryClient = useQueryClient();
  const { activeCaseId } = useCaseStore();
  const [personId, setPersonId] = useState('subject_alpha');

  // Mutation: Compute Baseline
  const computeBaselineMutation = useMutation({
    mutationFn: () => behavioralApi.computeBaseline(activeCaseId!, personId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['behavioral-baseline', activeCaseId, personId] });
    }
  });

  // Mutation: Scan Anomalies
  const scanAnomaliesMutation = useMutation({
    mutationFn: () => behavioralApi.scanAnomalies(activeCaseId!, personId, '2026-01-01T00:00:00Z', '2026-12-31T23:59:59Z'),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['behavioral-anomalies', activeCaseId, personId] });
    }
  });

  const { data: baseline } = useQuery({
    queryKey: ['behavioral-baseline', activeCaseId, personId],
    queryFn: () => behavioralApi.computeBaseline(activeCaseId!, personId),
    enabled: !!activeCaseId && !!personId,
  });

  const { data: anomalies = [] } = useQuery({
    queryKey: ['behavioral-anomalies', activeCaseId, personId],
    queryFn: () => behavioralApi.scanAnomalies(activeCaseId!, personId, '2026-01-01T00:00:00Z', '2026-12-31T23:59:59Z'),
    enabled: !!activeCaseId && !!personId,
  });

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the behavioral profiler."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Behavioral Profiler" 
        description="Computes subject baseline event frequencies, detects deviation thresholds, and flags suspicious sequence anomalies."
        actions={
          <div className="flex gap-2">
            <Button 
              onClick={() => computeBaselineMutation.mutate()}
              disabled={computeBaselineMutation.isPending}
              className="bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-xs gap-1.5"
            >
              {computeBaselineMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : "CALCULATE BASELINE"}
            </Button>
            <Button 
              onClick={() => scanAnomaliesMutation.mutate()}
              disabled={scanAnomaliesMutation.isPending}
              className="bg-intel-red hover:bg-intel-red/80 text-text-primary font-mono font-bold text-xs gap-1.5 shadow-[0_0_15px_rgba(244,63,94,0.2)]"
            >
              {scanAnomaliesMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : "SCAN ANOMALIES"}
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Side: Subject Details & Baseline */}
        <div className="lg:col-span-5 space-y-6">
          <IntelCard>
            <IntelCardHeader>
              <IntelCardTitle>
                <User className="w-4.5 h-4.5 text-intel-blue" />
                <span>Subject Baseline Parameters</span>
              </IntelCardTitle>
            </IntelCardHeader>
            <IntelCardContent className="space-y-4">
              <div className="space-y-1">
                <span className="text-[9px] font-mono text-text-secondary uppercase">Selected Subject Reference</span>
                <input
                  type="text"
                  value={personId}
                  onChange={(e) => setPersonId(e.target.value)}
                  className="w-full bg-base border border-border rounded-lg px-3 py-1.5 text-xs font-mono text-text-primary focus:outline-none focus:border-intel-blue/60"
                />
              </div>

              {baseline ? (
                <div className="space-y-3 pt-3 border-t border-border-subtle/50">
                  <div className="flex justify-between items-center bg-base/50 p-2.5 rounded border border-border-subtle text-xs font-mono">
                    <span className="text-text-secondary">Avg event interval (hours)</span>
                    <span className="text-text-primary font-bold">{baseline.average_event_interval_hours?.toFixed(2) || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-[9px] font-mono font-bold text-text-secondary uppercase">Event Frequency Distribution</span>
                    <pre className="bg-base/20 border border-border-subtle p-3 rounded-lg font-mono text-[10px] text-intel-cyan mt-1.5">
                      {JSON.stringify(baseline.event_type_frequencies, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="text-center py-6 text-text-muted font-mono text-xs">
                  No baseline computed for subject.
                </div>
              )}
            </IntelCardContent>
          </IntelCard>
        </div>

        {/* Right Side: Anomalies detected */}
        <div className="lg:col-span-7 space-y-6">
          <IntelCard>
            <IntelCardHeader>
              <IntelCardTitle>
                <Activity className="w-4.5 h-4.5 text-intel-red animate-pulse" />
                <span>Sequence Anomaly Registry</span>
              </IntelCardTitle>
            </IntelCardHeader>
            <IntelCardContent className="space-y-4">
              {anomalies.length === 0 ? (
                <div className="text-center py-10 text-text-muted font-mono text-xs border border-dashed border-border rounded-lg bg-surface/10">
                  No behavioral anomalies flagged in temporal window.
                </div>
              ) : (
                <div className="space-y-3">
                  {anomalies.map((anom) => (
                    <div key={anom.id} className="p-3 bg-base border border-border-subtle rounded-lg flex flex-col gap-2 relative overflow-hidden">
                      <div className="flex justify-between items-start">
                        <span className="text-[10px] font-mono font-bold text-intel-red uppercase tracking-wider bg-intel-red-dim/15 px-1.5 py-0.5 rounded border border-intel-red/20">
                          {anom.anomaly_type}
                        </span>
                        <SeverityIndicator severity={anom.severity} showIcon={false} />
                      </div>
                      <p className="text-xs font-bold text-text-primary">{anom.description}</p>
                      <div className="text-[9px] font-mono text-text-muted select-all">
                        Statistical basis: {anom.statistical_basis}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </IntelCardContent>
          </IntelCard>
        </div>
      </div>
    </div>
  );
}

// Quick helper
function cn(...classes: any[]) {
  return classes.filter(Boolean).join(' ');
}
