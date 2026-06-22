'use client';

import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { evidenceApi, ingestionApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { useSelectionStore } from '@/lib/store/selection.store';
import { 
  IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, 
  EmptyState, IntegrityGrade, IntelBadge, CopyButton
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { 
  FileText, ShieldCheck, Calendar, Hash, ArrowRight, 
  Upload, Filter, RefreshCw, Layers, HardDrive, CheckCircle2, ShieldAlert, X
} from 'lucide-react';
import { cn } from '@/lib/utils';

export default function EvidenceLabWorkspace() {
  const queryClient = useQueryClient();
  const { activeCaseId } = useCaseStore();
  const { panelSizes, setPanelSizes } = useWorkspaceStore();
  const { select } = useSelectionStore();
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [filterTag, setFilterTag] = useState<string>('all');
  const [showUploadSlideover, setShowUploadSlideover] = useState(false);

  // Form upload states
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [sourceTool, setSourceTool] = useState('Manual Upload');
  const [classification, setClassification] = useState('evidentiary');

  // Query: Get evidence list
  const { data: evidence = [], isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['evidence', activeCaseId],
    queryFn: () => evidenceApi.list(activeCaseId!),
    enabled: !!activeCaseId,
  });

  // Query: Get single evidence detail
  const { data: detailData, isLoading: isLoadingDetail } = useQuery({
    queryKey: ['evidence-detail', selectedArtifactId],
    queryFn: () => evidenceApi.get(selectedArtifactId!),
    enabled: !!selectedArtifactId,
  });

  // Query: Verify chain of custody
  const { data: verificationReport } = useQuery({
    queryKey: ['chain-verification', activeCaseId],
    queryFn: () => evidenceApi.verifyChain(activeCaseId!),
    enabled: !!activeCaseId,
  });

  // Mutation: Ingest evidence file
  const ingestMutation = useMutation({
    mutationFn: (formData: FormData) => ingestionApi.ingest(activeCaseId!, formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evidence', activeCaseId] });
      queryClient.invalidateQueries({ queryKey: ['chain-verification', activeCaseId] });
      setShowUploadSlideover(false);
      setUploadFile(null);
    }
  });

  const handleIngest = (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;

    const formData = new FormData();
    formData.append('file', uploadFile);
    formData.append('source_tool', sourceTool);
    formData.append('classification_tag', classification);

    ingestMutation.mutate(formData);
  };

  // Filter evidence
  const filteredEvidence = evidence.filter(item => {
    if (filterTag === 'all') return true;
    return item.classification_tag === filterTag;
  });

  // Get selected artifact
  const selectedArtifact = evidence.find(item => item.artifact_id === selectedArtifactId);

  // Compute integrity grade based on hash verification and verification report
  const getGradeForArtifact = (artId: string) => {
    const isBroken = verificationReport?.breaks?.some((b: any) => b.artifact_id === artId);
    if (isBroken) return "F";
    const artObj = evidence.find(i => i.artifact_id === artId);
    if (!artObj) return "D";
    if (artObj.previous_record_hash) return "A";
    return "B";
  };

  // Synchronize with selection store
  const handleSelectArtifact = (id: string) => {
    setSelectedArtifactId(id);
    const art = evidence.find(item => item.artifact_id === id);
    if (art) {
      select({
        id: art.artifact_id,
        type: 'evidence',
        name: art.content_pointer.split('/').pop(),
        metadata: {
          hash: art.content_hash,
          classification: art.classification_tag
        }
      });
    }
  };

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to browse the evidence vault."
      />
    );
  }

  return (
    <div className="h-full w-full flex flex-col overflow-hidden bg-base">
      
      {/* 1. TOP LEDGER SUMMARY & ACTIONS BAR */}
      <div className="h-10 border-b border-border bg-surface px-4 flex items-center justify-between shrink-0 select-none text-[10px] font-mono">
        <div className="flex items-center gap-3">
          <Layers className="w-4 h-4 text-intel-blue" />
          <span className="font-bold text-text-primary uppercase tracking-wider">
            Ledger Cryptographic Audit:
          </span>
          {verificationReport?.valid ? (
            <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-intel-green-dim/15 text-intel-green border border-intel-green/20 text-[9px] font-bold">
              <CheckCircle2 className="w-3 h-3" />
              <span>CHAIN VERIFIED</span>
            </div>
          ) : (
            <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-intel-red-dim/15 text-intel-red border border-intel-red/20 text-[9px] font-bold animate-pulse">
              <ShieldAlert className="w-3 h-3" />
              <span>CHAIN DISCREPANCY</span>
            </div>
          )}
          <span className="text-text-muted">|</span>
          <span className="text-text-secondary">
            {verificationReport?.artifacts_checked || 0} artifacts checked (SHA-256 Merkle root chain)
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Button 
            variant="secondary"
            onClick={() => refetch()}
            disabled={isLoading || isRefetching}
            className="h-6 px-2.5 font-mono text-[9px] border-border-subtle"
          >
            <RefreshCw className={isRefetching ? "w-3 h-3 animate-spin" : "w-3 h-3"} />
          </Button>
          <Button 
            onClick={() => setShowUploadSlideover(true)}
            className="h-6 px-3 bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-[9px] gap-1 shrink-0"
          >
            <Upload className="w-3 h-3" />
            <span>INGEST ARTIFACT</span>
          </Button>
        </div>
      </div>

      {/* 2. SPLIT RESIZABLE PANEL CONTAINER */}
      <div className="flex-1 min-h-0 w-full relative">
        <PanelGroup 
          orientation="horizontal" 
          onLayoutChanged={(layout) => setPanelSizes('evidence-lab', Object.values(layout))}
        >
          {/* Left Panel: Ingested Artifacts List */}
          <Panel id="el-left" defaultSize={panelSizes['evidence-lab'][0]} minSize={25} className="h-full flex flex-col overflow-hidden bg-base">
            <div className="p-3 border-b border-border bg-surface/40 flex items-center justify-between shrink-0 select-none">
              <div className="flex items-center gap-1 text-[9px] font-mono font-bold text-text-secondary uppercase">
                <Filter className="w-3 h-3 text-text-muted" />
                <span>Filters</span>
              </div>
              <select
                value={filterTag}
                onChange={(e) => setFilterTag(e.target.value)}
                className="bg-transparent text-[9px] font-mono text-text-primary focus:outline-none border-none cursor-pointer"
              >
                <option value="all">ALL CLASSIFICATIONS</option>
                <option value="public_osint">OSINT // PUBLIC</option>
                <option value="case_sensitive">RESTRICTED</option>
                <option value="pii">PII // SECURE</option>
                <option value="evidentiary">EVIDENTIARY</option>
                <option value="legal_privileged">LEGAL PRIVILEGED</option>
              </select>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-thin">
              {isLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((_, i) => (
                    <div key={i} className="h-12 rounded bg-surface animate-pulse" />
                  ))}
                </div>
              ) : filteredEvidence.length === 0 ? (
                <div className="text-center py-8 text-text-muted font-mono text-[9px] border border-dashed border-border rounded bg-surface/5">
                  No artifacts match filters.
                </div>
              ) : (
                filteredEvidence.map((item) => {
                  const isSelected = item.artifact_id === selectedArtifactId;
                  const grade = getGradeForArtifact(item.artifact_id);
                  return (
                    <div
                      key={item.artifact_id}
                      onClick={() => handleSelectArtifact(item.artifact_id)}
                      className={cn(
                        "p-2.5 rounded border transition-all duration-150 cursor-pointer flex justify-between items-center",
                        isSelected 
                          ? "bg-intel-blue-dim/15 border-intel-blue/40 shadow-sm" 
                          : "bg-surface border-border-subtle hover:border-border/60"
                      )}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className={cn(
                          "h-7 w-7 rounded flex items-center justify-center shrink-0 border border-border-subtle",
                          isSelected ? "bg-intel-blue-dim/20 text-intel-blue" : "bg-elevated text-text-secondary"
                        )}>
                          <FileText className="w-3.5 h-3.5" />
                        </div>
                        <div className="min-w-0 flex flex-col">
                          <span className="text-[10px] font-bold text-text-primary truncate font-sans">
                            {item.content_pointer.split('/').pop()}
                          </span>
                          <span className="text-[8px] font-mono text-text-muted truncate select-all">
                            {item.artifact_id.slice(0, 8)}...
                          </span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1.5 shrink-0 ml-3">
                        <IntegrityGrade grade={grade} size="sm" />
                        <span className="text-[7.5px] font-mono text-text-muted">
                          {new Date(item.collection_timestamp_utc).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle className="w-[1px] hover:w-[3px] bg-border hover:bg-intel-blue transition-all duration-150 relative cursor-col-resize h-full" />

          {/* Right Panel: Artifact details */}
          <Panel id="el-right" defaultSize={panelSizes['evidence-lab'][1]} minSize={40} className="h-full flex flex-col overflow-hidden bg-surface border-l border-border">
            {selectedArtifactId && selectedArtifact ? (
              <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
                
                {/* Header detail */}
                <div className="flex justify-between items-start border-b border-border pb-3">
                  <div>
                    <h2 className="text-xs font-bold text-text-primary font-mono flex items-center gap-1.5 break-all">
                      <FileText className="w-4.5 h-4.5 text-intel-blue" />
                      <span>{selectedArtifact.content_pointer.split('/').pop()}</span>
                    </h2>
                    <p className="text-[8px] font-mono text-text-muted mt-1 select-all">
                      UUID: {selectedArtifact.artifact_id}
                    </p>
                  </div>
                  <IntegrityGrade grade={getGradeForArtifact(selectedArtifact.artifact_id)} size="md" />
                </div>

                {/* Technical parameters */}
                <div className="grid grid-cols-2 gap-3 bg-base/40 p-3 border border-border-subtle rounded text-[9.5px] font-mono">
                  <div className="space-y-0.5">
                    <span className="text-[8px] text-text-secondary uppercase">Source Ingestion Tool</span>
                    <p className="font-bold text-text-primary">{selectedArtifact.source_tool}</p>
                  </div>
                  <div className="space-y-0.5">
                    <span className="text-[8px] text-text-secondary uppercase">Acquisition UTC Time</span>
                    <p className="font-bold text-text-primary">
                      {new Date(selectedArtifact.collection_timestamp_utc).toLocaleString()}
                    </p>
                  </div>
                  <div className="space-y-0.5">
                    <span className="text-[8px] text-text-secondary uppercase">Timezone Context</span>
                    <p className="font-bold text-text-primary">{selectedArtifact.original_timezone}</p>
                  </div>
                  <div className="space-y-0.5">
                    <span className="text-[8px] text-text-secondary uppercase">Classification Level</span>
                    <div>
                      <IntelBadge tag={selectedArtifact.classification_tag} size="sm" />
                    </div>
                  </div>
                </div>

                {/* Cryptographic Ledger Block details */}
                <div className="space-y-2">
                  <h4 className="text-[9px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                    Cryptographic Ledger Parameters
                  </h4>
                  <div className="bg-base/30 p-2.5 border border-border-subtle rounded flex items-center justify-between gap-4 text-[9.5px] font-mono">
                    <div className="min-w-0 flex items-center gap-2">
                      <Hash className="w-3.5 h-3.5 text-text-muted shrink-0" />
                      <div className="min-w-0">
                        <span className="text-[8px] text-text-secondary uppercase">SHA-256 Signature</span>
                        <p className="font-bold text-text-primary truncate select-all">{selectedArtifact.content_hash}</p>
                      </div>
                    </div>
                    <CopyButton value={selectedArtifact.content_hash} className="shrink-0" />
                  </div>
                  
                  {selectedArtifact.previous_record_hash && (
                    <div className="bg-base/15 p-2.5 border border-border-subtle rounded flex items-center justify-between gap-4 text-[9.5px] font-mono">
                      <div className="min-w-0 flex items-center gap-2">
                        <Layers className="w-3.5 h-3.5 text-text-muted shrink-0" />
                        <div className="min-w-0">
                          <span className="text-[8px] text-text-secondary uppercase">Merkle Previous Signature Link</span>
                          <p className="text-text-muted truncate select-all">{selectedArtifact.previous_record_hash}</p>
                        </div>
                      </div>
                      <CopyButton value={selectedArtifact.previous_record_hash} className="shrink-0" />
                    </div>
                  )}
                </div>

                {/* Chain of Custody History */}
                <div className="space-y-2.5">
                  <h4 className="text-[9px] font-mono font-bold text-text-secondary uppercase tracking-wider">
                    Chain of Custody Ledger Logs
                  </h4>
                  <div className="relative border-l border-border-subtle ml-2 pl-4 space-y-3 font-mono text-[9px]">
                    {selectedArtifact.chain_of_custody_log?.map((log, idx) => (
                      <div key={idx} className="relative">
                        <div className="absolute -left-[20.5px] top-1 h-2 w-2 rounded-full bg-intel-blue border border-obsidian shadow-[0_0_6px_rgba(74,158,255,0.4)]" />
                        <div className="flex flex-col gap-0.5">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-text-primary">{log.action}</span>
                            <span className="text-[8px] text-text-muted">by {log.actor}</span>
                          </div>
                          <span className="text-[8px] text-text-muted">
                            {new Date(log.timestamp).toLocaleString()}
                          </span>
                          {log.notes && (
                            <p className="text-[9.5px] text-text-secondary font-sans leading-relaxed mt-1 bg-obsidian/30 p-2 rounded border border-border-subtle/40 select-all">
                              {log.notes}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

              </div>
            ) : (
              <EmptyState 
                title="No artifact selected" 
                description="Click on any evidence artifact from the ledger list on the left to inspect its cryptographic signature, chain of custody logs, and metadata parameters."
                icon={HardDrive}
              />
            )}
          </Panel>
        </PanelGroup>
      </div>

      {/* Upload Slideover Overlay */}
      {showUploadSlideover && (
        <>
          <div 
            className="fixed inset-0 bg-obsidian/75 backdrop-blur-sm z-40 animate-in fade-in"
            onClick={() => setShowUploadSlideover(false)}
          />
          <div className="fixed top-0 right-0 h-full w-full max-w-sm bg-overlay border-l border-border shadow-2xl z-50 p-5 flex flex-col justify-between animate-in slide-in-from-right duration-250 font-mono text-[10px]">
            <div className="space-y-5">
              <div className="flex justify-between items-center border-b border-border-subtle pb-3">
                <div>
                  <h3 className="text-xs font-bold text-text-primary flex items-center gap-2">
                    <Upload className="w-4 h-4 text-intel-blue" />
                    <span>Upload & Ingest Evidence</span>
                  </h3>
                  <p className="text-[9px] text-text-secondary mt-1">
                    Adds file contents to Postgres, hashes metadata, and appends to Neo4j.
                  </p>
                </div>
                <button 
                  onClick={() => setShowUploadSlideover(false)}
                  className="text-text-secondary hover:text-text-primary"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleIngest} className="space-y-4">
                {/* File picker */}
                <div className="space-y-1">
                  <label className="text-[8px] font-bold uppercase tracking-wider text-text-secondary">
                    Target File
                  </label>
                  <div className="border border-dashed border-border hover:border-intel-blue/40 rounded p-6 flex flex-col items-center justify-center bg-base/50 text-center cursor-pointer transition-colors relative">
                    <input 
                      type="file" 
                      onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                      className="absolute inset-0 opacity-0 cursor-pointer text-[0px]"
                      required
                    />
                    <Upload className="w-6 h-6 text-text-secondary mb-1" />
                    {uploadFile ? (
                      <div className="space-y-0.5">
                        <p className="text-[10px] font-bold text-text-primary break-all px-2">{uploadFile.name}</p>
                        <p className="text-[8px] text-text-muted">{(uploadFile.size / 1024).toFixed(2)} KB</p>
                      </div>
                    ) : (
                      <div>
                        <p className="text-[10px] font-semibold text-text-primary">Drag & Drop or Click to Select</p>
                        <p className="text-[8px] text-text-muted mt-0.5">Accepts raw evidence logs, documents, etc.</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Source Tool */}
                <div className="space-y-1">
                  <label className="text-[8px] font-bold uppercase tracking-wider text-text-secondary">
                    Ingestion Source Tool
                  </label>
                  <input
                    type="text"
                    value={sourceTool}
                    onChange={(e) => setSourceTool(e.target.value)}
                    className="w-full bg-base border border-border rounded px-2.5 py-1.5 text-[10px] text-text-primary focus:outline-none focus:border-intel-blue/50"
                    placeholder="e.g. Wireshark, Volatility, Manual"
                    required
                  />
                </div>

                {/* Classification Tag */}
                <div className="space-y-1">
                  <label className="text-[8px] font-bold uppercase tracking-wider text-text-secondary">
                    Security Clearances Tag
                  </label>
                  <select
                    value={classification}
                    onChange={(e) => setClassification(e.target.value)}
                    className="w-full bg-base border border-border rounded px-2.5 py-1.5 text-[10px] text-text-primary focus:outline-none focus:border-intel-blue/50"
                  >
                    <option value="public_osint">OSINT // PUBLIC</option>
                    <option value="case_sensitive">RESTRICTED</option>
                    <option value="pii">PII // SECURE</option>
                    <option value="evidentiary">EVIDENTIARY</option>
                    <option value="legal_privileged">LEGAL PRIVILEGED</option>
                  </select>
                </div>

                <Button 
                  type="submit" 
                  className="w-full bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-bold text-[10px] mt-4 py-2 rounded shadow-md"
                  disabled={ingestMutation.isPending}
                >
                  {ingestMutation.isPending ? "INGESTING AND CALIBRATING..." : "EXECUTE INGEST"}
                </Button>
              </form>
            </div>
            
            <div className="text-[8px] text-text-muted text-center leading-normal mt-4 border-t border-border-subtle pt-3 select-none">
              SECURE SHA-256 LEDGER PROTOCOL ENABLED. SUBMISSIONS ARE IRREVERSIBLE AND AUDITED.
            </div>
          </div>
        </>
      )}
    </div>
  );
}
