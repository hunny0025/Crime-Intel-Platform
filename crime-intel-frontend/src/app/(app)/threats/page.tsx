'use client';

import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { nationalApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { 
  PageHeader, IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, 
  EmptyState, SeverityIndicator 
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { ShieldAlert, Play, RefreshCw, Loader2, CheckCircle2 } from 'lucide-react';

export default function ThreatsPage() {
  const queryClient = useQueryClient();
  const { activeCaseId } = useCaseStore();

  const { data: signals = [], isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['national-threats'],
    queryFn: nationalApi.getThreatSignals,
  });

  const detectMutation = useMutation({
    mutationFn: () => nationalApi.detectThreatSignals(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['national-threats'] });
    }
  });

  return (
    <div className="space-y-6">
      <PageHeader 
        title="National Threat Directory" 
        description="Unified national intelligence feed detecting anomalies and alerts across agencies."
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
              onClick={() => detectMutation.mutate()}
              disabled={detectMutation.isPending}
              className="bg-intel-red hover:bg-intel-red/80 text-text-primary font-mono font-bold text-xs gap-1.5 shadow-[0_0_15px_rgba(244,63,94,0.2)]"
            >
              {detectMutation.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5" />
              )}
              <span>TRIGGER THREAT DETECTION</span>
            </Button>
          </div>
        }
      />

      <div className="space-y-4">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((_, i) => (
              <div key={i} className="h-24 bg-surface rounded animate-pulse" />
            ))}
          </div>
        ) : signals.length === 0 ? (
          <EmptyState 
            title="Threat directory is clean" 
            description="No active threat signals detected. Trigger detection to index feeds."
            icon={CheckCircle2}
          />
        ) : (
          signals.map((sig, idx) => (
            <IntelCard key={idx} glowColor="red">
              <IntelCardHeader className="py-4">
                <div className="flex justify-between items-start gap-4">
                  <div>
                    <span className="text-[10px] font-mono font-bold text-intel-red uppercase tracking-wider bg-intel-red-dim/15 px-1.5 py-0.5 rounded border border-intel-red/20">
                      {sig.threat_type || 'THREAT'}
                    </span>
                    <h3 className="text-sm font-bold text-text-primary mt-2">
                      {sig.description}
                    </h3>
                  </div>
                  <div className="text-right">
                    <span className="text-[9px] font-mono text-text-muted">Anomaly Score</span>
                    <p className="text-xs font-mono font-bold text-intel-red mt-0.5">{sig.anomaly_score?.toFixed(3) || '0.920'}</p>
                  </div>
                </div>
              </IntelCardHeader>
              <IntelCardContent className="py-2 text-[11px] font-mono text-text-secondary flex justify-between">
                <span>Source: {sig.source_system || 'INTERPOL'}</span>
                <span>Detected: {new Date(sig.detected_at || Date.now()).toLocaleString()}</span>
              </IntelCardContent>
            </IntelCard>
          ))
        )}
      </div>
    </div>
  );
}
