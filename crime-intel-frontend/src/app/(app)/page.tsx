'use client';

import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { 
  casesApi, graphApi, nationalApi, intelligenceApi 
} from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { cn } from '@/lib/utils';
import { 
  Folder, Database, Network, Brain, AlertOctagon, 
  ShieldAlert, Activity, Cpu, CheckCircle2, ChevronRight,
  RefreshCw, TrendingUp, AlertTriangle, Scale, Hammer
} from 'lucide-react';
import ReactECharts from 'echarts-for-react';

export default function MissionControlWorkspace() {
  const { activeCaseId, activeCase } = useCaseStore();
  const { panelSizes, setPanelSizes } = useWorkspaceStore();

  // Queries
  const { data: cases = [], isLoading: isLoadingCases } = useQuery({
    queryKey: ['cases'],
    queryFn: casesApi.list
  });

  const { data: graphSummary } = useQuery({
    queryKey: ['graph-summary', activeCaseId],
    queryFn: () => graphApi.getSummary(activeCaseId!),
    enabled: !!activeCaseId
  });

  const { data: threatSignals = [] } = useQuery({
    queryKey: ['threat-signals'],
    queryFn: nationalApi.getThreatSignals
  });

  const { data: actionQueue = [] } = useQuery({
    queryKey: ['action-queue', activeCaseId],
    queryFn: () => intelligenceApi.listActionQueue(activeCaseId!),
    enabled: !!activeCaseId
  });

  // Calculate stats
  const stats = useMemo(() => {
    const nodeCount = graphSummary 
      ? Object.values(graphSummary.node_counts).reduce((a, b) => (a as number) + (b as number), 0)
      : 0;
    const edgeCount = graphSummary 
      ? Object.values(graphSummary.relationship_counts).reduce((a, b) => (a as number) + (b as number), 0)
      : 0;
    
    return {
      casesCount: cases.length,
      artifactsCount: graphSummary?.node_counts?.EvidenceArtifact || 0,
      entitiesCount: nodeCount,
      hypothesesCount: graphSummary?.node_counts?.Hypothesis || 0,
      contradictionsCount: graphSummary?.node_counts?.Contradiction || 0,
      edgesCount: edgeCount
    };
  }, [cases, graphSummary]);

  // ECharts: Kafka Processing Queue Lag
  const lagChartOption = useMemo(() => ({
    backgroundColor: 'transparent',
    grid: { left: '2%', right: '2%', top: '5%', bottom: '5%', containLabel: true },
    tooltip: { 
      trigger: 'axis', 
      backgroundColor: '#1c2029', 
      borderColor: '#1e2330', 
      textStyle: { color: '#e2e5ed', fontSize: 10, fontFamily: 'JetBrains Mono' } 
    },
    xAxis: {
      type: 'category',
      data: ['10:00', '10:05', '10:10', '10:15', '10:20', '10:25', '10:30', '10:35', '10:40', '10:45', '10:50', '10:55'],
      axisLine: { lineStyle: { color: '#1e2330' } },
      axisLabel: { fontFamily: 'JetBrains Mono', fontSize: 8, color: '#7e8ca3' }
    },
    yAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: '#1e2330' } },
      splitLine: { lineStyle: { color: '#161a21' } },
      axisLabel: { fontFamily: 'JetBrains Mono', fontSize: 8, color: '#7e8ca3' }
    },
    series: [
      {
        name: 'Event Ingestion Lag',
        type: 'line',
        smooth: true,
        data: [120, 110, 85, 45, 12, 5, 48, 92, 140, 75, 30, 8],
        lineStyle: { color: '#4a9eff', width: 1.5 },
        itemStyle: { color: '#4a9eff' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(74, 158, 255, 0.15)' },
              { offset: 1, color: 'rgba(74, 158, 255, 0.0)' }
            ]
          }
        }
      }
    ]
  }), []);

  // Pipeline Stages
  const pipelineStages = [
    { name: 'INTAKE', status: 'completed' },
    { name: 'PARSING', status: 'completed' },
    { name: 'GRAPH POP', status: 'completed' },
    { name: 'IDENTITY RES', status: 'active' },
    { name: 'NLP ENRICH', status: 'pending' },
    { name: 'LEGAL CHECK', status: 'pending' }
  ];

  return (
    <div className="h-full w-full flex flex-col overflow-hidden bg-base">
      
      {/* 1. TOP PIPELINE STATUS BAR */}
      <div className="h-8 border-b border-border bg-surface px-4 flex items-center justify-between shrink-0 select-none text-[9px] font-mono">
        <div className="flex items-center gap-1.5 text-text-secondary">
          <Activity className="w-3.5 h-3.5 text-intel-blue" />
          <span className="font-bold">INVESTIGATION PIPELINE:</span>
        </div>
        
        <div className="flex items-center gap-4">
          {pipelineStages.map((stage, i) => (
            <React.Fragment key={stage.name}>
              <div className="flex items-center gap-1.5">
                <div className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  stage.status === 'completed' && "bg-intel-green shadow-[0_0_6px_#34d399]",
                  stage.status === 'active' && "bg-intel-blue animate-pulse shadow-[0_0_6px_#4a9eff]",
                  stage.status === 'pending' && "bg-text-muted"
                )} />
                <span className={cn(
                  stage.status === 'completed' && "text-intel-green font-bold",
                  stage.status === 'active' && "text-intel-blue font-bold",
                  stage.status === 'pending' && "text-text-muted"
                )}>
                  {stage.name}
                </span>
              </div>
              {i < pipelineStages.length - 1 && <ChevronRight className="w-3 h-3 text-text-muted" />}
            </React.Fragment>
          ))}
        </div>

        <div className="flex items-center gap-1.5 text-text-secondary pl-3 border-l border-border-subtle">
          <RefreshCw className="w-2.5 h-2.5 animate-spin" />
          <span>Real-time Ingestion Live</span>
        </div>
      </div>

      {/* 2. SPLIT LAYOUT AREA */}
      <div className="flex-1 min-h-0 w-full relative">
        <PanelGroup 
          orientation="horizontal" 
          onLayoutChanged={(layout) => setPanelSizes('mission-control', Object.values(layout))}
        >
          {/* Left Panel: Stats and Cases Matrix */}
          <Panel id="mc-left" defaultSize={panelSizes['mission-control'][0]} minSize={40} className="h-full flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
              
              {/* Telemetry Stats Rows */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <div className="bg-surface border border-border rounded p-3 flex flex-col justify-between">
                  <div className="flex justify-between items-center text-[10px] text-text-secondary font-mono">
                    <span>Investigations</span>
                    <Folder className="w-3.5 h-3.5 text-intel-blue" />
                  </div>
                  <div className="text-xl font-bold tracking-tight text-text-primary mt-2 font-mono">{stats.casesCount}</div>
                </div>

                <div className="bg-surface border border-border rounded p-3 flex flex-col justify-between">
                  <div className="flex justify-between items-center text-[10px] text-text-secondary font-mono">
                    <span>Evidence Files</span>
                    <Database className="w-3.5 h-3.5 text-intel-cyan" />
                  </div>
                  <div className="text-xl font-bold tracking-tight text-text-primary mt-2 font-mono">{stats.artifactsCount}</div>
                </div>

                <div className="bg-surface border border-border rounded p-3 flex flex-col justify-between">
                  <div className="flex justify-between items-center text-[10px] text-text-secondary font-mono">
                    <span>Entities Indexed</span>
                    <Network className="w-3.5 h-3.5 text-intel-green" />
                  </div>
                  <div className="text-xl font-bold tracking-tight text-text-primary mt-2 font-mono">{stats.entitiesCount}</div>
                </div>

                <div className="bg-surface border border-border rounded p-3 flex flex-col justify-between">
                  <div className="flex justify-between items-center text-[10px] text-text-secondary font-mono">
                    <span>Legal Audits</span>
                    <Scale className="w-3.5 h-3.5 text-intel-purple" />
                  </div>
                  <div className="text-xl font-bold tracking-tight text-text-primary mt-2 font-mono">78%</div>
                </div>
              </div>

              {/* Case Matrix Table */}
              <div className="bg-surface border border-border rounded flex flex-col overflow-hidden">
                <div className="border-b border-border p-3 flex items-center justify-between bg-obsidian/40 select-none">
                  <div className="flex items-center gap-2">
                    <Folder className="w-3.5 h-3.5 text-intel-blue" />
                    <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-primary">
                      Neo4j Cluster Investigations
                    </span>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left font-mono text-[10px] border-collapse">
                    <thead>
                      <tr className="border-b border-border bg-obsidian/25 text-text-secondary">
                        <th className="p-2.5 font-bold uppercase tracking-wider">Case Reference</th>
                        <th className="p-2.5 font-bold uppercase tracking-wider">Crime Type</th>
                        <th className="p-2.5 font-bold uppercase tracking-wider">Classification</th>
                        <th className="p-2.5 font-bold uppercase tracking-wider">Telemetry State</th>
                        <th className="p-2.5 font-bold uppercase tracking-wider text-right">Last Sync</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle bg-surface">
                      {cases.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="p-6 text-center text-text-muted">No cases loaded.</td>
                        </tr>
                      ) : (
                        cases.map((c) => (
                          <tr key={c.case_id} className="hover:bg-elevated/40 transition-colors">
                            <td className="p-2.5 text-intel-blue font-bold select-all">{c.case_id.slice(0, 12)}...</td>
                            <td className="p-2.5 text-text-primary">{c.case_type}</td>
                            <td className="p-2.5">
                              <span className={cn(
                                "px-1.5 py-0.2 rounded text-[8px] font-bold border",
                                c.classification_tag === "public_osint" && "bg-intel-cyan-dim/15 text-intel-cyan border-intel-cyan/30",
                                c.classification_tag === "case_sensitive" && "bg-intel-amber-dim/15 text-intel-amber border-intel-amber/30",
                                c.classification_tag === "evidentiary" && "bg-intel-red-dim/15 text-intel-red border-intel-red/30",
                                c.classification_tag === "legal_privileged" && "bg-intel-purple-dim/15 text-intel-purple border-intel-purple/30"
                              )}>
                                {c.classification_tag.replace('_', ' ').toUpperCase()}
                              </span>
                            </td>
                            <td className="p-2.5 text-text-secondary uppercase">{c.status.replace('_', ' ')}</td>
                            <td className="p-2.5 text-right text-text-muted">{new Date(c.updated_at).toLocaleString()}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Ingestion Telemetry Lag */}
              <div className="bg-surface border border-border rounded p-3">
                <div className="flex justify-between items-center mb-3">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-primary">
                    Real-time Ingestion Lag (Ticks)
                  </span>
                  <span className="text-[8px] font-mono text-text-muted">Updated 5s ago</span>
                </div>
                <ReactECharts option={lagChartOption} style={{ height: 120 }} />
              </div>

            </div>
          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle className="w-[1px] hover:w-[3px] bg-border hover:bg-intel-blue transition-all duration-150 relative cursor-col-resize h-full" />

          {/* Right Panel: ORACLE summary and activity feeds */}
          <Panel id="mc-right" defaultSize={panelSizes['mission-control'][1]} minSize={20} className="h-full flex flex-col overflow-hidden border-l border-border bg-surface">
            <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
              
              {/* ORACLE summary */}
              <div className="bg-obsidian/50 border border-border rounded p-3 space-y-2.5">
                <div className="flex items-center gap-1.5 text-intel-purple font-mono text-[10px] font-bold">
                  <Brain className="w-3.5 h-3.5" />
                  <span>ORACLE EXECUTIVE INSIGHTS</span>
                </div>
                {activeCase ? (
                  <>
                    <p className="text-[10px] font-mono text-text-secondary leading-relaxed">
                      Active case analysis points to critical targets in the domain of <span className="text-text-primary font-bold">{activeCase.case_type}</span>. Identity resolution completed with high confidence metrics.
                    </p>
                    <div className="bg-surface border border-border-subtle p-2 rounded text-[9px] font-mono text-text-muted">
                      💡 Recommended Action: Query OSINT details for recently resolved communication channels.
                    </div>
                  </>
                ) : (
                  <p className="text-[9px] font-mono text-text-muted">
                    Select an active case from the top command bar to initialize the ORACLE co-analyst summary.
                  </p>
                )}
              </div>

              {/* Threat Signals list */}
              <div className="bg-surface border border-border rounded flex flex-col overflow-hidden">
                <div className="border-b border-border p-3 flex items-center justify-between bg-obsidian/40 select-none">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="w-3.5 h-3.5 text-intel-red" />
                    <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-primary">
                      Jurisdiction Threat Stream
                    </span>
                  </div>
                </div>
                <div className="p-3 space-y-2 max-h-[300px] overflow-y-auto scrollbar-thin">
                  {threatSignals.length === 0 ? (
                    <div className="text-center py-4 text-text-muted font-mono text-[9px]">
                      No anomalous stream alerts active.
                    </div>
                  ) : (
                    threatSignals.map((signal, idx) => (
                      <div 
                        key={idx} 
                        className="p-2.5 bg-obsidian border border-border-subtle rounded space-y-1"
                      >
                        <div className="flex justify-between items-center text-[8px] font-mono">
                          <span className="text-intel-red font-bold uppercase bg-intel-red-dim/15 px-1 py-0.2 rounded border border-intel-red/25">
                            {signal.threat_type || 'ANOMALY'}
                          </span>
                          <span className="text-text-muted">Score: {signal.anomaly_score?.toFixed(2) || '0.90'}</span>
                        </div>
                        <p className="text-[9.5px] font-medium text-text-primary leading-tight font-mono">
                          {signal.description}
                        </p>
                        <div className="flex justify-between items-center text-[7.5px] text-text-muted pt-0.5">
                          <span>Source: {signal.source_system}</span>
                          <span>{new Date(signal.detected_at).toLocaleTimeString()}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

            </div>
          </Panel>
        </PanelGroup>
      </div>

    </div>
  );
}
