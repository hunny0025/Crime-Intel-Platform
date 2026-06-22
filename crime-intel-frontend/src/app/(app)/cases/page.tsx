'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { casesApi, ingestionApi, acquisitionApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { useWorkspaceStore } from '@/lib/store/workspace.store';
import { useSelectionStore } from '@/lib/store/selection.store';
import { useAuthStore } from '@/lib/store/auth.store';
import { 
  IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, IntelCardFooter,
  EmptyState, IntelBadge, Table, TableHeader, TableBody, TableRow, TableCell, TableHead
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { 
  FolderPlus, FolderOpen, ShieldCheck, User, Plus, Loader2, 
  RefreshCw, HardDrive, Cpu, Laptop, FileText, CheckCircle2, 
  History, Server, Play, ShieldAlert, PlusCircle, Radio, Wrench
} from 'lucide-react';
import { cn } from '@/lib/utils';

export default function CasesPage() {
  const queryClient = useQueryClient();
  const { activeCaseId, activeCase, setActiveCase } = useCaseStore();
  const { panelSizes, setPanelSizes } = useWorkspaceStore();
  const { select } = useSelectionStore();
  const { user } = useAuthStore();

  // Active sub-tab on the right panel
  const [activeTab, setActiveTab] = useState<'ingestion' | 'acquisition' | 'equipment'>('ingestion');

  // Dialog / form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [caseType, setCaseType] = useState('Cyber Espionage');
  const [classification, setClassification] = useState('case_sensitive');

  // Form states for registering lab equipment
  const [showEquipForm, setShowEquipForm] = useState(false);
  const [equipName, setEquipName] = useState('');
  const [equipType, setEquipType] = useState('Write Blocker');
  const [equipSerial, setEquipSerial] = useState('');
  const [equipLocation, setEquipLocation] = useState('Digital Forensics Lab - Station 1');

  // Form states for creating acquisition job
  const [showAcqForm, setShowAcqForm] = useState(false);
  const [selectedDeviceIndex, setSelectedDeviceIndex] = useState<number>(-1);
  const [acqMethod, setAcqMethod] = useState('physical');
  const [officerBadge, setOfficerBadge] = useState('');

  // Queries
  const { data: cases = [], isLoading: isLoadingCases, refetch: refetchCases } = useQuery({
    queryKey: ['cases'],
    queryFn: casesApi.list
  });

  const { data: ingestionLogs = [], isLoading: isLoadingIngestion, refetch: refetchIngestion } = useQuery({
    queryKey: ['ingestion-logs', activeCaseId],
    queryFn: () => ingestionApi.getAuditLog(activeCaseId!),
    enabled: !!activeCaseId,
  });

  const { data: connectedDevices = [], refetch: refetchDevices, isLoading: isLoadingDevices } = useQuery({
    queryKey: ['connected-devices'],
    queryFn: () => acquisitionApi.detectDevices().then(res => res.devices || []),
  });

  const { data: labInventory, refetch: refetchInventory, isLoading: isLoadingInventory } = useQuery({
    queryKey: ['lab-inventory'],
    queryFn: acquisitionApi.getInventory,
  });

  // Mutations
  const createCaseMutation = useMutation({
    mutationFn: (data: { case_type: string; classification_tag: any; created_by: string; status: any }) => 
      casesApi.create(data),
    onSuccess: (newCase) => {
      queryClient.invalidateQueries({ queryKey: ['cases'] });
      setActiveCase(newCase);
      setShowCreateForm(false);
    }
  });

  const registerEquipmentMutation = useMutation({
    mutationFn: (data: { equipment_id: string; name: string; equipment_type: string; serial_number: string; lab_location: string }) =>
      acquisitionApi.registerEquipment(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lab-inventory'] });
      setShowEquipForm(false);
      setEquipName('');
      setEquipSerial('');
    }
  });

  const createAcqJobMutation = useMutation({
    mutationFn: (data: any) => acquisitionApi.createJob(data),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ['lab-inventory'] });
      setShowAcqForm(false);
      // Automatically start job in simulation mode
      if (job && job.job_id) {
        startAcqJobMutation.mutate(job.job_id);
      }
    }
  });

  const startAcqJobMutation = useMutation({
    mutationFn: (jobId: string) => acquisitionApi.startJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['lab-inventory'] });
    }
  });

  const handleCreateCase = (e: React.FormEvent) => {
    e.preventDefault();
    createCaseMutation.mutate({
      case_type: caseType,
      classification_tag: classification,
      created_by: user || 'investigator_alpha',
      status: 'open'
    });
  };

  const handleRegisterEquipment = (e: React.FormEvent) => {
    e.preventDefault();
    registerEquipmentMutation.mutate({
      equipment_id: `EQUIP-${Math.floor(Math.random() * 10000)}`,
      name: equipName,
      equipment_type: equipType,
      serial_number: equipSerial,
      lab_location: equipLocation
    });
  };

  const handleCreateAcqJob = (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedDeviceIndex === -1 || !activeCaseId) return;

    const device = connectedDevices[selectedDeviceIndex] || {
      model: "Simulated Drive",
      serial: "SIM-88219-X",
      interface: "SATA",
      size_bytes: 500000000000,
      device_type: "hard_drive"
    };

    createAcqJobMutation.mutate({
      device,
      case_id: activeCaseId,
      method: acqMethod,
      output_dir: `./forensic_images/${activeCaseId}`,
      officer_name: user || 'Investigator',
      officer_badge: officerBadge || 'BADGE-9912',
      write_blocker_id: labInventory?.write_blockers?.[0]?.blocker_id || `BLOCKER-${Math.floor(Math.random() * 1000)}`
    });
  };

  const handleSelectCase = (c: any) => {
    setActiveCase(c);
    select({
      id: c.case_id,
      type: 'custom',
      name: `Case File: ${c.case_type}`,
      metadata: {
        case_id: c.case_id,
        classification: c.classification_tag,
        status: c.status
      }
    });
  };

  return (
    <div className="h-full w-full flex flex-col overflow-hidden bg-base">
      
      {/* Page Header Area */}
      <div className="h-10 border-b border-border bg-surface px-4 flex items-center justify-between shrink-0 select-none text-[10px] font-mono">
        <div className="flex items-center gap-1.5 text-text-secondary">
          <FolderOpen className="w-3.5 h-3.5 text-intel-blue" />
          <span>CASE SETUP & ACQUISITION SUITE</span>
        </div>

        <div className="flex items-center gap-2">
          <Button 
            variant="secondary"
            onClick={() => {
              refetchCases();
              if (activeCaseId) refetchIngestion();
              refetchDevices();
              refetchInventory();
            }}
            className="h-6 px-2.5 font-mono text-[9px] border-border-subtle"
          >
            <RefreshCw className="w-3 h-3" />
          </Button>
          <Button 
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="h-6 px-3 bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-[9px] gap-1 shrink-0"
          >
            <Plus className="w-3 h-3" />
            <span>INITIALIZE CASE</span>
          </Button>
        </div>
      </div>

      {/* Main Resizable Layout */}
      <div className="flex-1 min-h-0 w-full relative">
        <PanelGroup 
          orientation="horizontal" 
          onLayoutChanged={(layout) => setPanelSizes('case-setup', Object.values(layout))}
        >
          {/* Left Panel: Case Directory / Form */}
          <Panel id="cs-left" defaultSize={panelSizes['case-setup']?.[0] || 50} minSize={35} className="h-full flex flex-col overflow-hidden bg-base">
            <div className="p-3 border-b border-border bg-surface/40 flex items-center justify-between shrink-0 select-none text-[10px] font-mono font-bold text-text-secondary uppercase">
              <span>Active Investigation Vault</span>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
              {showCreateForm && (
                <IntelCard glowColor="blue" className="mb-4">
                  <IntelCardHeader>
                    <IntelCardTitle>
                      <FolderPlus className="w-4 h-4 text-intel-blue" />
                      <span>Initialize Case File</span>
                    </IntelCardTitle>
                  </IntelCardHeader>
                  <form onSubmit={handleCreateCase}>
                    <IntelCardContent className="space-y-3 font-mono text-[9.5px]">
                      <div className="space-y-1">
                        <label className="text-[8px] font-bold text-text-secondary uppercase">Category</label>
                        <input
                          type="text"
                          value={caseType}
                          onChange={(e) => setCaseType(e.target.value)}
                          className="w-full bg-base border border-border rounded px-2 py-1.5 text-[10px] text-text-primary focus:outline-none focus:border-intel-blue/50"
                          placeholder="e.g. Cyber Espionage, Financial Fraud"
                          required
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[8px] font-bold text-text-secondary uppercase">Security Classification</label>
                        <select
                          value={classification}
                          onChange={(e) => setClassification(e.target.value)}
                          className="w-full bg-base border border-border rounded px-2.5 py-1.5 text-[10px] text-text-primary focus:outline-none focus:border-intel-blue/50"
                        >
                          <option value="public_osint">OSINT // PUBLIC</option>
                          <option value="case_sensitive">RESTRICTED // SENSITIVE</option>
                          <option value="pii">PII // SECURE</option>
                          <option value="evidentiary">EVIDENTIARY</option>
                          <option value="legal_privileged">LEGAL // PRIVILEGED</option>
                        </select>
                      </div>
                    </IntelCardContent>
                    <IntelCardFooter className="flex justify-end gap-2 p-3">
                      <Button type="button" variant="secondary" onClick={() => setShowCreateForm(false)} className="h-6 px-2.5 text-[9px] font-mono">
                        CANCEL
                      </Button>
                      <Button type="submit" className="h-6 px-3 bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-[9px]" disabled={createCaseMutation.isPending}>
                        {createCaseMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : "CONFIRM"}
                      </Button>
                    </IntelCardFooter>
                  </form>
                </IntelCard>
              )}

              {isLoadingCases ? (
                <div className="flex justify-center items-center py-20">
                  <Loader2 className="w-6 h-6 animate-spin text-intel-blue" />
                </div>
              ) : cases.length === 0 ? (
                <EmptyState 
                  title="No active cases found" 
                  description="Initialize your first investigation file to connect to Neo4j graph nodes."
                  action={
                    <Button onClick={() => setShowCreateForm(true)} className="h-6 px-3 bg-intel-blue hover:bg-intel-blue/80 text-obsidian text-[9px] font-mono font-bold">
                      INITIALIZE CASE
                    </Button>
                  }
                />
              ) : (
                <div className="space-y-2">
                  {cases.map((c) => {
                    const isActive = c.case_id === activeCaseId;
                    return (
                      <div 
                        key={c.case_id}
                        onClick={() => handleSelectCase(c)}
                        className={cn(
                          "p-3 rounded border transition-all duration-150 cursor-pointer flex justify-between items-center",
                          isActive 
                            ? "bg-intel-blue-dim/10 border-intel-blue/40 shadow-sm" 
                            : "bg-surface border-border-subtle hover:border-border/60"
                        )}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div className={cn(
                            "h-7 w-7 rounded flex items-center justify-center shrink-0 border border-border-subtle",
                            isActive ? "bg-intel-blue-dim/20 text-intel-blue" : "bg-elevated text-text-secondary"
                          )}>
                            <FolderOpen className="w-3.5 h-3.5" />
                          </div>
                          <div className="min-w-0 flex flex-col font-mono text-[9px]">
                            <span className="font-bold text-text-primary truncate">
                              {c.case_type}
                            </span>
                            <span className="text-[8px] text-text-muted truncate select-all">
                              ID: {c.case_id}
                            </span>
                          </div>
                        </div>

                        <div className="flex flex-col items-end gap-1.5 shrink-0 ml-3">
                          <span className={cn(
                            "px-1.5 rounded text-[8px] font-bold border font-mono",
                            c.classification_tag === "public_osint" && "bg-intel-cyan-dim/15 text-intel-cyan border-intel-cyan/30",
                            c.classification_tag === "case_sensitive" && "bg-intel-amber-dim/15 text-intel-amber border-intel-amber/30",
                            c.classification_tag === "evidentiary" && "bg-intel-red-dim/15 text-intel-red border-intel-red/30",
                            c.classification_tag === "legal_privileged" && "bg-intel-purple-dim/15 text-intel-purple border-intel-purple/30"
                          )}>
                            {c.classification_tag.replace('_', ' ').toUpperCase()}
                          </span>
                          
                          {isActive ? (
                            <div className="inline-flex items-center gap-1 text-intel-green text-[8px] font-bold">
                              <ShieldCheck className="w-3 h-3" />
                              <span>ACTIVE</span>
                            </div>
                          ) : (
                            <span className="text-[8px] text-text-muted capitalize">
                              {c.status.replace('_', ' ')}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle className="w-[1px] hover:w-[3px] bg-border hover:bg-intel-blue transition-all duration-150 relative cursor-col-resize h-full" />

          {/* Right Panel: Ingestion Audits / Hardware Acquisition */}
          <Panel id="cs-right" defaultSize={panelSizes['case-setup']?.[1] || 50} minSize={35} className="h-full flex flex-col overflow-hidden bg-surface border-l border-border">
            
            {/* Header Tabs selector */}
            <div className="h-9 border-b border-border bg-surface/80 flex items-center justify-between px-3 shrink-0 select-none text-[9.5px] font-mono">
              <div className="flex gap-2">
                <button
                  onClick={() => setActiveTab('ingestion')}
                  className={cn(
                    "px-2.5 py-1 rounded transition-colors",
                    activeTab === 'ingestion' ? "bg-elevated text-intel-blue border border-border" : "text-text-secondary hover:text-text-primary"
                  )}
                >
                  INGESTION AUDIT TRACE
                </button>
                <button
                  onClick={() => setActiveTab('acquisition')}
                  className={cn(
                    "px-2.5 py-1 rounded transition-colors",
                    activeTab === 'acquisition' ? "bg-elevated text-intel-blue border border-border" : "text-text-secondary hover:text-text-primary"
                  )}
                >
                  DEVICES & FORENSIC JOBS
                </button>
                <button
                  onClick={() => setActiveTab('equipment')}
                  className={cn(
                    "px-2.5 py-1 rounded transition-colors",
                    activeTab === 'equipment' ? "bg-elevated text-intel-blue border border-border" : "text-text-secondary hover:text-text-primary"
                  )}
                >
                  LAB HARDWARE
                </button>
              </div>
            </div>

            {/* Content pane */}
            <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
              
              {/* Active Tab: Ingestion Logs */}
              {activeTab === 'ingestion' && (
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] font-mono font-bold text-text-secondary uppercase">Ingestion Stream Logging</span>
                    <span className="text-[8px] font-mono text-text-muted">Filtered by Active Case</span>
                  </div>

                  {!activeCaseId ? (
                    <div className="text-center py-12 text-text-muted font-mono text-[9px]">
                      Select an active case to display ingestion event history.
                    </div>
                  ) : isLoadingIngestion ? (
                    <div className="flex justify-center items-center py-10">
                      <Loader2 className="w-5 h-5 animate-spin text-intel-blue" />
                    </div>
                  ) : ingestionLogs.length === 0 ? (
                    <div className="text-center py-12 text-text-muted font-mono text-[9px] border border-dashed border-border rounded bg-base/5">
                      No ingestion runs recorded for this case file yet.
                    </div>
                  ) : (
                    <div className="space-y-2.5">
                      {ingestionLogs.map((log: any) => (
                        <div key={log.audit_id} className="p-3 bg-base border border-border-subtle rounded font-mono text-[9px] space-y-2">
                          <div className="flex justify-between items-start">
                            <div className="flex items-center gap-1.5">
                              <History className="w-3.5 h-3.5 text-intel-blue" />
                              <span className="font-bold text-text-primary">Source: {log.source_format}</span>
                            </div>
                            <span className="text-text-muted">{new Date(log.timestamp).toLocaleString()}</span>
                          </div>
                          
                          <div className="grid grid-cols-2 gap-2 text-text-secondary pt-1 border-t border-border-subtle/50">
                            <div>
                              <span>Officer: </span>
                              <span className="text-text-primary font-semibold">{log.actor}</span>
                            </div>
                            <div>
                              <span>Artifacts Created: </span>
                              <span className="text-text-primary font-bold">{log.num_artifacts}</span>
                            </div>
                          </div>

                          <div className="bg-obsidian/30 p-1.5 rounded flex items-center justify-between text-[8px] select-all mt-1">
                            <span className="text-text-muted">Kafka Event:</span>
                            <span className="text-intel-green font-bold">{log.kafka_event_id}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Active Tab: Forensic Jobs */}
              {activeTab === 'acquisition' && (
                <div className="space-y-4">
                  
                  {/* Title & Actions */}
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] font-mono font-bold text-text-secondary uppercase">Seized Device Imaging Suite</span>
                    {activeCaseId && (
                      <Button
                        onClick={() => setShowAcqForm(!showAcqForm)}
                        className="h-5 px-2 bg-intel-blue hover:bg-intel-blue/80 text-obsidian text-[8px] font-mono font-bold flex items-center gap-1"
                      >
                        <PlusCircle className="w-3 h-3" />
                        <span>IMAGE NEW DRIVE</span>
                      </Button>
                    )}
                  </div>

                  {/* Create Forensic Job Form */}
                  {showAcqForm && (
                    <IntelCard glowColor="amber" className="mb-4">
                      <IntelCardHeader>
                        <IntelCardTitle>
                          <HardDrive className="w-4 h-4 text-intel-amber" />
                          <span className="text-[10px]">Create Forensic Image Job</span>
                        </IntelCardTitle>
                      </IntelCardHeader>
                      <form onSubmit={handleCreateAcqJob}>
                        <IntelCardContent className="space-y-3 font-mono text-[9px]">
                          <div className="space-y-1">
                            <label className="text-[8px] font-bold text-text-secondary uppercase">Select Seized Hardware</label>
                            {connectedDevices.length === 0 ? (
                              <div className="p-2 border border-border rounded bg-base/50 text-text-muted text-[8px]">
                                No connected forensic media found. Will simulate SATA standard drive.
                              </div>
                            ) : (
                              <select
                                value={selectedDeviceIndex}
                                onChange={(e) => setSelectedDeviceIndex(parseInt(e.target.value))}
                                className="w-full bg-base border border-border rounded px-2 py-1.5 text-[9px] text-text-primary focus:outline-none"
                              >
                                <option value="-1">-- Simulated SATA Standard Drive --</option>
                                {connectedDevices.map((dev: any, idx: number) => (
                                  <option key={idx} value={idx}>
                                    {dev.model || "Disk"} ({dev.serial}) - {dev.size_gb || "N/A"} GB
                                  </option>
                                ))}
                              </select>
                            )}
                          </div>

                          <div className="grid grid-cols-2 gap-2">
                            <div className="space-y-1">
                              <label className="text-[8px] font-bold text-text-secondary uppercase">Imaging Method</label>
                              <select
                                value={acqMethod}
                                onChange={(e) => setAcqMethod(e.target.value)}
                                className="w-full bg-base border border-border rounded px-2 py-1.5 text-[9px] text-text-primary focus:outline-none"
                              >
                                <option value="physical">Physical (Bit-Stream dd/E01)</option>
                                <option value="logical">Logical (File-System extraction)</option>
                                <option value="file_system">Mounted System copy</option>
                                <option value="manual">Manual file extraction</option>
                              </select>
                            </div>
                            <div className="space-y-1">
                              <label className="text-[8px] font-bold text-text-secondary uppercase">Officer Badge #</label>
                              <input
                                type="text"
                                value={officerBadge}
                                onChange={(e) => setOfficerBadge(e.target.value)}
                                className="w-full bg-base border border-border rounded px-2 py-1.5 text-[9px] text-text-primary focus:outline-none"
                                placeholder="BADGE-9901"
                                required
                              />
                            </div>
                          </div>
                        </IntelCardContent>
                        <IntelCardFooter className="flex justify-end gap-2 p-2.5">
                          <Button type="button" variant="secondary" onClick={() => setShowAcqForm(false)} className="h-5 px-2.5 text-[8px] font-mono">
                            CANCEL
                          </Button>
                          <Button type="submit" className="h-5 px-3 bg-intel-amber hover:bg-intel-amber/80 text-obsidian font-mono font-bold text-[8px]">
                            START FORENSIC IMAGING
                          </Button>
                        </IntelCardFooter>
                      </form>
                    </IntelCard>
                  )}

                  {/* Active Imaging Jobs */}
                  <div className="space-y-2.5">
                    <span className="text-[8.5px] font-bold text-text-muted tracking-wider uppercase font-mono block">Acquisition Pipelines</span>
                    
                    {isLoadingInventory ? (
                      <div className="flex justify-center py-6">
                        <Loader2 className="w-4 h-4 animate-spin text-intel-blue" />
                      </div>
                    ) : !labInventory?.active_acquisitions || labInventory.active_acquisitions.length === 0 ? (
                      <div className="text-center py-6 text-text-muted font-mono text-[9px] border border-dashed border-border rounded bg-base/5">
                        No active or historic acquisition jobs registered.
                      </div>
                    ) : (
                      labInventory.active_acquisitions.map((job: any) => (
                        <div key={job.job_id} className="p-3 bg-base border border-border-subtle rounded font-mono text-[9px] space-y-2">
                          <div className="flex justify-between items-center">
                            <div className="flex items-center gap-1.5">
                              <Cpu className="w-3.5 h-3.5 text-intel-blue" />
                              <span className="font-bold text-text-primary">Job: {job.job_id.slice(0, 13)}</span>
                            </div>
                            <span className={cn(
                              "px-1.5 py-0.2 rounded text-[7.5px] font-bold border",
                              job.status === 'completed' && "bg-intel-green-dim/15 text-intel-green border-intel-green/20",
                              job.status === 'in_progress' && "bg-intel-blue-dim/15 text-intel-blue border-intel-blue/20 animate-pulse",
                              job.status === 'failed' && "bg-intel-red-dim/15 text-intel-red border-intel-red/20"
                            )}>
                              {job.status.toUpperCase()}
                            </span>
                          </div>

                          <div className="space-y-1 text-text-secondary">
                            <div>Seized Model: <span className="text-text-primary font-bold">{job.source_device?.model || 'Unknown'}</span></div>
                            <div>Acquisition Mode: <span className="text-text-primary">{job.method}</span></div>
                            <div>Forensic Custody: <span className="text-text-primary">Officer {job.officer}</span></div>
                          </div>

                          {job.hash_sha256 && (
                            <div className="bg-obsidian/30 p-1.5 rounded flex items-center justify-between text-[8px] select-all mt-1">
                              <span className="text-text-muted">SHA-256:</span>
                              <span className="text-text-primary truncate ml-2 max-w-[200px]">{job.hash_sha256}</span>
                            </div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              {/* Active Tab: Lab Equipment */}
              {activeTab === 'equipment' && (
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] font-mono font-bold text-text-secondary uppercase">Laboratory Equipment Directory</span>
                    <Button
                      onClick={() => setShowEquipForm(!showEquipForm)}
                      className="h-5 px-2 bg-intel-blue hover:bg-intel-blue/80 text-obsidian text-[8px] font-mono font-bold flex items-center gap-1"
                    >
                      <PlusCircle className="w-3 h-3" />
                      <span>REGISTER HARDWARE</span>
                    </Button>
                  </div>

                  {showEquipForm && (
                    <IntelCard glowColor="purple" className="mb-4">
                      <IntelCardHeader>
                        <IntelCardTitle>
                          <Wrench className="w-4 h-4 text-intel-purple" />
                          <span className="text-[10px]">Register Lab Equipment</span>
                        </IntelCardTitle>
                      </IntelCardHeader>
                      <form onSubmit={handleRegisterEquipment}>
                        <IntelCardContent className="space-y-3 font-mono text-[9px]">
                          <div className="grid grid-cols-2 gap-2">
                            <div className="space-y-1">
                              <label className="text-[8px] font-bold text-text-secondary uppercase">Equipment Name</label>
                              <input
                                type="text"
                                value={equipName}
                                onChange={(e) => setEquipName(e.target.value)}
                                className="w-full bg-base border border-border rounded px-2 py-1.5 text-[9px] text-text-primary focus:outline-none"
                                placeholder="e.g. Tableau T8u Write Blocker"
                                required
                              />
                            </div>
                            <div className="space-y-1">
                              <label className="text-[8px] font-bold text-text-secondary uppercase">Hardware Type</label>
                              <select
                                value={equipType}
                                onChange={(e) => setEquipType(e.target.value)}
                                className="w-full bg-base border border-border rounded px-2.5 py-1.5 text-[9px] text-text-primary focus:outline-none"
                              >
                                <option value="Write Blocker">Write Blocker</option>
                                <option value="Faraday Bag">Faraday Bag</option>
                                <option value="Imaging Station">Imaging Workstation</option>
                                <option value="Cryptographic Decryptor">Decryptor Accelerator</option>
                              </select>
                            </div>
                          </div>

                          <div className="grid grid-cols-2 gap-2">
                            <div className="space-y-1">
                              <label className="text-[8px] font-bold text-text-secondary uppercase">Serial Number</label>
                              <input
                                type="text"
                                value={equipSerial}
                                onChange={(e) => setEquipSerial(e.target.value)}
                                className="w-full bg-base border border-border rounded px-2 py-1.5 text-[9px] text-text-primary focus:outline-none"
                                placeholder="S/N: 29910-AA2"
                                required
                              />
                            </div>
                            <div className="space-y-1">
                              <label className="text-[8px] font-bold text-text-secondary uppercase">Lab Location Room</label>
                              <input
                                type="text"
                                value={equipLocation}
                                onChange={(e) => setEquipLocation(e.target.value)}
                                className="w-full bg-base border border-border rounded px-2 py-1.5 text-[9px] text-text-primary focus:outline-none"
                                required
                              />
                            </div>
                          </div>
                        </IntelCardContent>
                        <IntelCardFooter className="flex justify-end gap-2 p-2.5">
                          <Button type="button" variant="secondary" onClick={() => setShowEquipForm(false)} className="h-5 px-2.5 text-[8px] font-mono">
                            CANCEL
                          </Button>
                          <Button type="submit" className="h-5 px-3 bg-intel-purple hover:bg-intel-purple/80 text-obsidian font-mono font-bold text-[8px]">
                            REGISTER HARDWARE
                          </Button>
                        </IntelCardFooter>
                      </form>
                    </IntelCard>
                  )}

                  {/* Registered Equipment Inventory */}
                  <div className="space-y-2.5">
                    {isLoadingInventory ? (
                      <div className="flex justify-center py-6">
                        <Loader2 className="w-4 h-4 animate-spin text-intel-blue" />
                      </div>
                    ) : !labInventory?.equipment || labInventory.equipment.length === 0 ? (
                      <div className="text-center py-6 text-text-muted font-mono text-[9px] border border-dashed border-border rounded bg-base/5">
                        No hardware registered. Register write-blockers or Faraday bags using the action above.
                      </div>
                    ) : (
                      labInventory.equipment.map((eq: any) => (
                        <div key={eq.equipment_id} className="p-3 bg-base border border-border-subtle rounded font-mono text-[9px] space-y-2">
                          <div className="flex justify-between items-center">
                            <span className="font-bold text-text-primary">{eq.name}</span>
                            <span className="px-1 py-0.2 rounded text-[7.5px] font-bold border bg-intel-green-dim/15 text-intel-green border-intel-green/20">
                              {eq.type.toUpperCase()}
                            </span>
                          </div>
                          
                          <div className="grid grid-cols-2 gap-2 text-text-secondary text-[8.5px]">
                            <div>Serial: <span className="text-text-primary font-mono">{eq.serial_number}</span></div>
                            <div>Location: <span className="text-text-primary">{eq.lab_location}</span></div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

            </div>
          </Panel>
        </PanelGroup>
      </div>

    </div>
  );
}
