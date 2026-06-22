'use client';

import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useCaseStore } from '@/lib/store/case.store';
import { graphApi, nationalApi } from '@/lib/api/client';
import { Database, ShieldAlert, Cpu } from 'lucide-react';
import { cn } from '@/lib/utils';

export function StatusBar() {
  const { activeCaseId } = useCaseStore();

  // Query graph summary for stats
  const { data: graphSummary } = useQuery({
    queryKey: ['graph-summary', activeCaseId],
    queryFn: () => graphApi.getSummary(activeCaseId!),
    enabled: !!activeCaseId,
  });

  // Query platform health
  const { data: healthData } = useQuery({
    queryKey: ['platform-health'],
    queryFn: nationalApi.getPlatformHealth,
    refetchInterval: 20000, // every 20s
  });

  // Aggregate node and relationship counts
  const stats = useMemo(() => {
    if (!graphSummary) return { nodes: 0, edges: 0, evidence: 0 };
    const nodes = Object.values(graphSummary.node_counts || {}).reduce((a, b) => a + b, 0);
    const edges = Object.values(graphSummary.relationship_counts || {}).reduce((a, b) => a + b, 0);
    const evidence = graphSummary.node_counts?.EvidenceArtifact || 0;
    return { nodes, edges, evidence };
  }, [graphSummary]);

  const pgStatus = healthData?.services?.postgres?.status === 'healthy';
  const neoStatus = healthData?.services?.neo4j?.status === 'healthy';

  return (
    <footer className="h-6 bg-obsidian border-t border-border px-4 flex items-center justify-between shrink-0 select-none text-[10px] font-mono text-text-secondary z-20">
      {/* Left: Pipeline Telemetry & Database Health */}
      <div className="flex items-center gap-4">
        {/* PostgreSQL status */}
        <div className="flex items-center gap-1">
          <Database className="w-3 h-3 text-text-muted" />
          <span>PG:</span>
          <span className={cn('font-bold', pgStatus ? 'text-intel-green' : 'text-intel-red')}>
            {pgStatus ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
        </div>

        {/* Neo4j Graph DB status */}
        <div className="flex items-center gap-1 border-l border-border-subtle pl-4">
          <Cpu className="w-3 h-3 text-text-muted" />
          <span>GRAPH:</span>
          <span className={cn('font-bold', neoStatus ? 'text-intel-green' : 'text-intel-red')}>
            {neoStatus ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
        </div>
      </div>

      {/* Center: Graph Stats */}
      <div className="flex items-center gap-3">
        {activeCaseId ? (
          <>
            <span>Case Graph:</span>
            <span className="text-text-primary font-bold">{stats.nodes} nodes</span>
            <span className="text-text-muted">·</span>
            <span className="text-text-primary font-bold">{stats.edges} edges</span>
            <span className="text-text-muted">·</span>
            <span className="text-text-primary font-bold">{stats.evidence} files</span>
          </>
        ) : (
          <span>No active case loaded</span>
        )}
      </div>

      {/* Right: Legal compliance status & engine health */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <ShieldAlert className="w-3 h-3 text-text-muted" />
          <span>Legal score:</span>
          <span className="text-intel-blue font-bold">78%</span>
        </div>
        <div className="border-l border-border-subtle pl-3 flex items-center gap-1.5">
          <div className="h-1.5 w-1.5 rounded-full bg-intel-green shadow-[0_0_6px_#34d399]" />
          <span>System Idle</span>
        </div>
      </div>
    </footer>
  );
}
