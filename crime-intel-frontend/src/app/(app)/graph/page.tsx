'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import ReactFlow, { 
  MiniMap, Controls, Background, useNodesState, useEdgesState, 
  MarkerType, NodeProps, Handle, Position
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useQuery } from '@tanstack/react-query';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { casesApi, graphApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { useSelectionStore } from '@/lib/store/selection.store';
import { 
  IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent,
  EmptyState, EntityChip, SeverityIndicator, ConfidenceBar, ProbabilityDisplay
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { 
  User, Laptop, AtSign, MapPin, Calendar, Brain, 
  AlertOctagon, HelpCircle, FileText, Search, ZoomIn, 
  ZoomOut, Maximize2, LayoutGrid, Info, ShieldAlert, X
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ── CUSTOM NODE COMPONENTS ────────────────────────────────────────────────

const NodeWrapper = ({ children, borderClass, isSelected, title, icon: Icon }: any) => (
  <div className={`p-2 rounded-lg border bg-surface/90 backdrop-blur-sm min-w-[150px] shadow-lg transition-all duration-200 ${
    isSelected ? 'border-intel-blue shadow-[0_0_12px_rgba(74,158,255,0.25)] scale-105' : borderClass
  }`}>
    <div className="flex items-center gap-1.5 border-b border-border-subtle/50 pb-1 mb-1 select-none">
      <div className="p-0.5 rounded bg-elevated border border-border-subtle text-text-secondary">
        <Icon className="w-3 h-3" />
      </div>
      <span className="text-[8px] font-mono font-bold text-text-secondary uppercase tracking-wider">{title}</span>
    </div>
    {children}
  </div>
);

const CustomPersonNode = ({ data, selected }: NodeProps) => (
  <NodeWrapper borderClass="border-intel-blue/30" isSelected={selected} title="Person" icon={User}>
    <Handle type="target" position={Position.Top} className="bg-border" />
    <div className="space-y-0.5 text-[10px]">
      <p className="font-bold text-text-primary truncate">{data.display_name || data.id.slice(0, 8)}</p>
      <p className="font-mono text-text-muted text-[8px] capitalize truncate">Role: {data.role || 'Subject'}</p>
    </div>
    <Handle type="source" position={Position.Bottom} className="bg-border" />
  </NodeWrapper>
);

const CustomDeviceNode = ({ data, selected }: NodeProps) => (
  <NodeWrapper borderClass="border-intel-purple/30" isSelected={selected} title="Device" icon={Laptop}>
    <Handle type="target" position={Position.Top} className="bg-border" />
    <div className="space-y-0.5 text-[10px]">
      <p className="font-bold text-text-primary capitalize truncate">{data.device_type || 'Unknown'}</p>
      {data.identifiers && data.identifiers.length > 0 && (
        <p className="font-mono text-text-muted text-[7px] truncate select-all">{data.identifiers[0]}</p>
      )}
    </div>
    <Handle type="source" position={Position.Bottom} className="bg-border" />
  </NodeWrapper>
);

const CustomAccountNode = ({ data, selected }: NodeProps) => (
  <NodeWrapper borderClass="border-intel-cyan/30" isSelected={selected} title="Account" icon={AtSign}>
    <Handle type="target" position={Position.Top} className="bg-border" />
    <div className="space-y-0.5 text-[10px]">
      <p className="font-bold text-text-primary truncate">{data.platform || 'Platform'}</p>
      <p className="font-mono text-text-muted text-[8px] truncate">ID: {data.id.slice(0, 8)}</p>
    </div>
    <Handle type="source" position={Position.Bottom} className="bg-border" />
  </NodeWrapper>
);

const CustomLocationNode = ({ data, selected }: NodeProps) => (
  <NodeWrapper borderClass="border-intel-green/30" isSelected={selected} title="Location" icon={MapPin}>
    <Handle type="target" position={Position.Top} className="bg-border" />
    <div className="space-y-0.5 text-[10px]">
      <p className="font-bold text-text-primary truncate">{data.address || 'Address'}</p>
      {data.coordinates && (
        <p className="font-mono text-text-muted text-[7.5px] truncate">{data.coordinates}</p>
      )}
    </div>
    <Handle type="source" position={Position.Bottom} className="bg-border" />
  </NodeWrapper>
);

const CustomEventNode = ({ data, selected }: NodeProps) => (
  <NodeWrapper borderClass="border-intel-amber/30" isSelected={selected} title="Event" icon={Calendar}>
    <Handle type="target" position={Position.Top} className="bg-border" />
    <div className="space-y-0.5 text-[10px]">
      <p className="font-bold text-text-primary capitalize truncate">{data.event_type || 'Event'}</p>
      {data.valid_from && (
        <p className="font-mono text-text-muted text-[8px]">
          {new Date(data.valid_from).toLocaleDateString()}
        </p>
      )}
    </div>
    <Handle type="source" position={Position.Bottom} className="bg-border" />
  </NodeWrapper>
);

const CustomHypothesisNode = ({ data, selected }: NodeProps) => (
  <NodeWrapper borderClass="border-intel-magenta/30" isSelected={selected} title="Hypothesis" icon={Brain}>
    <Handle type="target" position={Position.Top} className="bg-border" />
    <div className="space-y-0.5 text-[10px]">
      <p className="font-bold text-text-primary line-clamp-2 leading-tight">{data.narrative}</p>
      {data.probability !== undefined && (
        <div className="pt-0.5 flex items-center justify-between">
          <span className="text-[8px] font-mono text-text-secondary">Prob:</span>
          <span className="text-[9px] font-mono font-bold text-intel-magenta">{Math.round(data.probability * 100)}%</span>
        </div>
      )}
    </div>
    <Handle type="source" position={Position.Bottom} className="bg-border" />
  </NodeWrapper>
);

const CustomContradictionNode = ({ data, selected }: NodeProps) => (
  <NodeWrapper borderClass="border-intel-red/30" isSelected={selected} title="Contradiction" icon={AlertOctagon}>
    <Handle type="target" position={Position.Top} className="bg-border" />
    <div className="space-y-0.5 text-[10px]">
      <p className="font-bold text-text-primary line-clamp-2 leading-tight">{data.description}</p>
      <div className="flex justify-between items-center pt-0.5">
        <span className="text-[7px] font-mono text-text-secondary uppercase">{data.contradiction_type}</span>
        <span className="text-[7.5px] font-mono font-bold text-intel-red capitalize">{data.severity}</span>
      </div>
    </div>
    <Handle type="source" position={Position.Bottom} className="bg-border" />
  </NodeWrapper>
);

const CustomEvidenceGapNode = ({ data, selected }: NodeProps) => (
  <NodeWrapper borderClass="border-intel-amber/30" isSelected={selected} title="Evidence Gap" icon={HelpCircle}>
    <Handle type="target" position={Position.Top} className="bg-border" />
    <div className="space-y-0.5 text-[10px]">
      <p className="font-bold text-text-primary line-clamp-2 leading-tight">{data.description}</p>
      <div className="flex justify-between items-center pt-0.5">
        <span className="text-[7.5px] font-mono text-text-secondary uppercase">Gap</span>
        <span className="text-[7.5px] font-mono font-bold text-intel-amber capitalize">{data.urgency} urgency</span>
      </div>
    </div>
    <Handle type="source" position={Position.Bottom} className="bg-border" />
  </NodeWrapper>
);

const nodeTypes = {
  Person: CustomPersonNode,
  Device: CustomDeviceNode,
  Account: CustomAccountNode,
  Location: CustomLocationNode,
  Event: CustomEventNode,
  Hypothesis: CustomHypothesisNode,
  Contradiction: CustomContradictionNode,
  EvidenceGap: CustomEvidenceGapNode,
};

const EMPTY_ENTITIES: any[] = [];

export default function GraphExplorerWorkspace() {
  const { activeCaseId } = useCaseStore();
  const { panelSizes, setPanelSizes } = useWorkspaceStore();
  const { selectedEntity, select } = useSelectionStore();
  const [selectedNode, setSelectedNode] = useState<any | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // 1. Fetch entities in Case
  const { data: entities = EMPTY_ENTITIES, isLoading: isLoadingEntities } = useQuery({
    queryKey: ['case-entities', activeCaseId],
    queryFn: () => casesApi.listEntities(activeCaseId!),
    enabled: !!activeCaseId,
  });

  // 2. Fetch timeline events for strip
  const { data: timelineEvents = [] } = useQuery({
    queryKey: ['timeline-strip', activeCaseId],
    queryFn: () => graphApi.getTimeline(activeCaseId!, '2026-01-01T00:00:00Z', '2026-12-31T23:59:59Z'),
    enabled: !!activeCaseId,
  });

  // 3. Fetch neighbors for entities
  const [loadedGraph, setLoadedGraph] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });
  const [loadingGraph, setLoadingGraph] = useState(false);

  useEffect(() => {
    if (entities.length === 0) {
      setLoadedGraph({ nodes: [], edges: [] });
      return;
    }

    const loadFullGraph = async () => {
      setLoadingGraph(true);
      try {
        const uniqueNodeIds = new Set<string>();
        const uniqueEdgeKeys = new Set<string>();
        const nodes: any[] = [];
        const edges: any[] = [];

        for (const entity of entities) {
          try {
            const neighbors = await graphApi.getNeighbors(activeCaseId!, entity.entity_id);
            for (const item of neighbors) {
              const neighborNode = item.node;
              const rel = item.relationship;

              if (!uniqueNodeIds.has(neighborNode.id)) {
                uniqueNodeIds.add(neighborNode.id);
                nodes.push(neighborNode);
              }

              const edgeKey = `${rel.from_node_id}-${rel.to_node_id}-${rel.type}`;
              if (!uniqueEdgeKeys.has(edgeKey)) {
                uniqueEdgeKeys.add(edgeKey);
                edges.push(rel);
              }
            }
          } catch (err) {
            console.error(`Failed to fetch neighbors for entity ${entity.entity_id}:`, err);
          }
        }

        setLoadedGraph({ nodes, edges });
      } catch (err) {
        console.error("Failed to build full graph:", err);
      } finally {
        setLoadingGraph(false);
      }
    };

    loadFullGraph();
  }, [entities, activeCaseId]);

  // React Flow state bindings
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Filtered graph items
  const filteredNodes = useMemo(() => {
    if (!searchQuery) return loadedGraph.nodes;
    return loadedGraph.nodes.filter(n => {
      const name = n.display_name || n.name || n.narrative || n.description || n.device_type || n.address || '';
      return name.toLowerCase().includes(searchQuery.toLowerCase()) || n.label.toLowerCase().includes(searchQuery.toLowerCase());
    });
  }, [loadedGraph.nodes, searchQuery]);

  // Convert nodes & edges to React Flow objects
  useEffect(() => {
    if (loadedGraph.nodes.length === 0) {
      if (nodes.length > 0) setNodes([]);
      if (edges.length > 0) setEdges([]);
      return;
    }

    const flowNodes = filteredNodes.map((node, index) => {
      const angle = (index / filteredNodes.length) * 2 * Math.PI;
      const radius = 220 + Math.random() * 40;
      const x = 300 + radius * Math.cos(angle);
      const y = 250 + radius * Math.sin(angle);

      return {
        id: node.id,
        type: node.label,
        data: node,
        position: { x, y }
      };
    });

    const flowEdges = loadedGraph.edges
      .filter(edge => {
        const hasSource = filteredNodes.some(n => n.id === edge.from_node_id);
        const hasTarget = filteredNodes.some(n => n.id === edge.to_node_id);
        return hasSource && hasTarget;
      })
      .map(edge => {
        const confidence = edge.confidence !== undefined ? edge.confidence : 1.0;
        return {
          id: `${edge.from_node_id}-${edge.to_node_id}-${edge.relationship_type}`,
          source: edge.from_node_id,
          target: edge.to_node_id,
          label: edge.relationship_type,
          type: 'default',
          animated: edge.relationship_type === 'CONTRADICTS' || edge.relationship_type === 'PREDICTED_BY',
          style: {
            stroke: edge.relationship_type === 'CONTRADICTS' ? '#f43f5e' : 'rgba(74, 158, 255, 0.45)',
            strokeWidth: 1.5,
            opacity: 0.3 + confidence * 0.7,
          },
          labelStyle: {
            fill: '#8b9ab8',
            fontSize: 7,
            fontFamily: 'JetBrains Mono',
            fontWeight: 'bold',
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 12,
            height: 12,
            color: edge.relationship_type === 'CONTRADICTS' ? '#f43f5e' : 'rgba(74, 158, 255, 0.45)',
          }
        };
      });

    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [loadedGraph.edges, filteredNodes, setNodes, setEdges]);

  // Handle local node click
  const onNodeClick = useCallback((event: React.MouseEvent, node: any) => {
    setSelectedNode(node.data);
    select({
      id: node.data.id,
      type: node.data.label.toLowerCase() as any,
      name: node.data.display_name || node.data.name || node.data.id,
      metadata: node.data
    });
  }, [select]);

  const handleSelectNodeById = useCallback((id: string) => {
    const nodeObj = loadedGraph.nodes.find(n => n.id === id);
    if (nodeObj) {
      setSelectedNode(nodeObj);
      select({
        id: nodeObj.id,
        type: nodeObj.label.toLowerCase() as any,
        name: nodeObj.display_name || nodeObj.name || nodeObj.id,
        metadata: nodeObj
      });
    }
  }, [loadedGraph.nodes, select]);

  // Synchronize layout selection triggers
  useEffect(() => {
    if (selectedEntity && selectedEntity.type !== 'custom') {
      const matchingNode = loadedGraph.nodes.find(n => n.id === selectedEntity.id);
      if (matchingNode && matchingNode !== selectedNode) {
        setSelectedNode(matchingNode);
      }
    }
  }, [selectedEntity, loadedGraph.nodes, selectedNode]);

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to render the interactive knowledge graph."
      />
    );
  }

  return (
    <div className="h-full w-full flex flex-col overflow-hidden bg-base">
      
      {/* 1. TOP HEADER SEARCH BAR */}
      <div className="h-10 border-b border-border bg-surface px-4 flex items-center justify-between shrink-0 select-none text-[10px] font-mono">
        <div className="flex items-center gap-1.5 text-text-secondary">
          <Info className="w-3.5 h-3.5 text-intel-blue" />
          <span>CYPHER SEARCH GATEWAY</span>
        </div>

        <div className="w-72 relative">
          <Search className="absolute left-2.5 top-1.5 h-3 w-3 text-text-secondary" />
          <input
            type="text"
            placeholder="Traverse query by name or ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-base border border-border rounded pl-8 pr-2 py-0.5 text-[9px] font-mono text-text-primary focus:outline-none focus:border-intel-blue/50"
          />
        </div>
      </div>

      {/* 2. SPLIT LAYOUT AREA */}
      <div className="flex-1 min-h-0 w-full relative">
        <PanelGroup 
          orientation="horizontal" 
          onLayoutChanged={(layout) => setPanelSizes('graph-explorer', Object.values(layout))}
        >
          {/* Left Panel: Graph Canvas + Sync Timeline Strip */}
          <Panel id="ge-left" defaultSize={panelSizes['graph-explorer'][0]} minSize={50} className="h-full flex flex-col overflow-hidden">
            
            {/* Graph Area */}
            <div className="flex-1 rounded-b border-b border-border bg-base overflow-hidden relative shadow-inner min-h-0">
              {loadingGraph ? (
                <div className="absolute inset-0 bg-obsidian/40 flex items-center justify-center z-10 font-mono text-[9px]">
                  <span className="text-intel-blue animate-pulse">TRAVERSING NEO4J INDEX PATHS...</span>
                </div>
              ) : nodes.length === 0 ? (
                <div className="absolute inset-0 flex items-center justify-center z-10 bg-surface/10">
                  <EmptyState 
                    title="Graph index empty" 
                    description="No nodes generated. Ingest evidence in the Vault to generate."
                  />
                </div>
              ) : null}

              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                nodeTypes={nodeTypes}
                onNodeClick={onNodeClick}
                fitView
              >
                <Controls className="bg-overlay border border-border text-text-primary" />
                <MiniMap 
                  nodeColor={(node) => {
                    switch(node.type) {
                      case 'Person': return '#4a9eff';
                      case 'Device': return '#a78bfa';
                      case 'Account': return '#22d3ee';
                      case 'Location': return '#2dd4bf';
                      case 'Event': return '#f59e0b';
                      case 'Hypothesis': return '#e879f9';
                      case 'Contradiction': return '#f43f5e';
                      default: return '#8b9ab8';
                    }
                  }}
                  maskColor="rgba(8, 10, 13, 0.6)"
                  className="bg-overlay border border-border"
                />
                <Background color="#161a21" gap={16} />
              </ReactFlow>
            </div>

            {/* Bottom Timeline Strip (Synchronized) */}
            <div className="h-14 border-t border-border bg-surface shrink-0 flex flex-col justify-between p-2 font-mono text-[9px] select-none">
              <span className="text-text-muted uppercase text-[8px] font-bold">Synchronized Timeline Strip</span>
              <div className="flex items-center gap-2 overflow-x-auto scrollbar-none py-1">
                {timelineEvents.length === 0 ? (
                  <span className="text-text-muted">No chronological metrics logged for active case.</span>
                ) : (
                  timelineEvents.map((t, idx) => {
                    const ev = t.event;
                    const dateStr = ev.valid_from ? new Date(ev.valid_from).toLocaleDateString() : 'N/A';
                    const isSelected = selectedNode?.id === ev.id;
                    return (
                      <button
                        key={idx}
                        onClick={() => handleSelectNodeById(ev.id)}
                        className={cn(
                          "px-2 py-0.5 rounded border text-left flex flex-col gap-0.2 shrink-0 transition-colors cursor-pointer",
                          isSelected
                            ? "bg-intel-blue-dim/20 text-intel-blue border-intel-blue/40 font-bold"
                            : "bg-base border-border hover:border-text-secondary text-text-secondary"
                        )}
                      >
                        <span className="truncate max-w-[100px] text-[8px] uppercase">{ev.event_type}</span>
                        <span className="text-[7.5px] text-text-muted font-bold">{dateStr}</span>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle className="w-[1px] hover:w-[3px] bg-border hover:bg-intel-blue transition-all duration-150 relative cursor-col-resize h-full" />

          {/* Right Panel: Detail Inspector */}
          <Panel id="ge-right" defaultSize={panelSizes['graph-explorer'][1]} minSize={20} className="h-full flex flex-col overflow-hidden bg-surface border-l border-border">
            {selectedNode ? (
              <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
                <div className="flex justify-between items-start border-b border-border pb-3">
                  <div>
                    <span className="text-[8px] font-mono font-bold text-intel-blue uppercase tracking-wider bg-intel-blue-dim/15 px-1.5 py-0.5 rounded border border-intel-blue/25">
                      {selectedNode.label || 'ENTITY'}
                    </span>
                    <h3 className="text-xs font-bold text-text-primary mt-2 break-all">
                      {selectedNode.display_name || selectedNode.name || selectedNode.narrative || selectedNode.description || selectedNode.device_type || selectedNode.address || selectedNode.id.slice(0, 12)}
                    </h3>
                  </div>
                  <button 
                    onClick={() => setSelectedNode(null)}
                    className="text-text-secondary hover:text-text-primary p-0.5"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Properties list */}
                <div className="space-y-3">
                  <h4 className="text-[9px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                    Node Properties
                  </h4>
                  
                  <div className="space-y-2 text-[9.5px] font-mono">
                    <div className="bg-base/40 p-2.5 rounded border border-border-subtle flex flex-col gap-0.5 select-all">
                      <span className="text-[8px] text-text-secondary uppercase">UUID</span>
                      <span className="text-text-primary break-all">{selectedNode.id}</span>
                    </div>

                    {selectedNode.classification_tag && (
                      <div className="flex justify-between items-center bg-base/20 p-2 border border-border-subtle/50 rounded">
                        <span className="text-[8px] text-text-secondary uppercase">Security Clearance</span>
                        <span className="px-1.5 py-0.2 rounded text-[8px] font-bold border bg-intel-blue-dim/10 text-intel-blue border-intel-blue/20">
                          {selectedNode.classification_tag.replace('_', ' ').toUpperCase()}
                        </span>
                      </div>
                    )}

                    {selectedNode.valid_from && (
                      <div className="flex justify-between items-center bg-base/20 p-2 border border-border-subtle/50 rounded">
                        <span className="text-[8px] text-text-secondary uppercase">Validation Timestamp</span>
                        <span className="text-text-primary">
                          {new Date(selectedNode.valid_from).toLocaleString()}
                        </span>
                      </div>
                    )}

                    {selectedNode.probability !== undefined && (
                      <div className="bg-base/20 p-2.5 border border-border-subtle rounded space-y-1.5">
                        <span className="text-[8px] text-text-secondary uppercase">Bayesian Probability</span>
                        <div className="flex justify-between items-center">
                          <ProbabilityDisplay value={selectedNode.probability} confidence={selectedNode.confidence_in_probability} />
                        </div>
                      </div>
                    )}

                    {selectedNode.severity && (
                      <div className="flex justify-between items-center bg-base/20 p-2 border border-border-subtle/50 rounded">
                        <span className="text-[8px] text-text-secondary uppercase">Severity Level</span>
                        <SeverityIndicator severity={selectedNode.severity} />
                      </div>
                    )}
                  </div>
                </div>

                {/* Narrative Summary */}
                <div className="space-y-2">
                  <h4 className="text-[9px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                    Intel Narrative / Description
                  </h4>
                  <p className="text-[10px] font-sans text-text-secondary leading-relaxed bg-base/20 p-3 rounded border border-border-subtle select-all">
                    {selectedNode.narrative || selectedNode.description || selectedNode.address || "No text description cataloged."}
                  </p>
                </div>
              </div>
            ) : (
              <EmptyState 
                title="No entity selected" 
                description="Click on any node in the knowledge graph or timeline strip to inspect details, parameters, and structural relationships."
                icon={Info}
              />
            )}
          </Panel>
        </PanelGroup>
      </div>

    </div>
  );
}
