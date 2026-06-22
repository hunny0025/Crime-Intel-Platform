import axios from 'axios';
import * as T from './types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Cases API
export const casesApi = {
  list: () => apiClient.get<T.Case[]>('/cases').then(res => res.data),
  get: (caseId: string) => apiClient.get<T.Case>(`/cases/${caseId}`).then(res => res.data),
  create: (data: { case_type: string; status: T.CaseStatus; classification_tag: T.ClassificationTag; created_by: string }) =>
    apiClient.post<T.Case>('/cases', data).then(res => res.data),
  listEntities: (caseId: string) => apiClient.get<T.CaseEntity[]>(`/cases/${caseId}/entities`).then(res => res.data),
  linkEntity: (caseId: string, data: { entity_id: string; entity_type: string; role: string }) =>
    apiClient.post<T.CaseEntity>(`/cases/${caseId}/entities`, data).then(res => res.data),
};

// Evidence API
export const evidenceApi = {
  list: (caseId: string) => apiClient.get<T.EvidenceArtifact[]>(`/cases/${caseId}/evidence`).then(res => res.data),
  get: (artifactId: string) => apiClient.get<T.EvidenceArtifact & { presigned_url?: string }>(`/evidence/${artifactId}`).then(res => res.data),
  upload: (caseId: string, formData: FormData) =>
    apiClient.post<T.EvidenceArtifact>(`/cases/${caseId}/evidence`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(res => res.data),
  verifyChain: (caseId: string) =>
    apiClient.get<{ valid: boolean; artifacts_checked: number; breaks: any[] }>(`/cases/${caseId}/chain-of-custody/verify`).then(res => res.data),
};

// Ingestion API
export const ingestionApi = {
  ingest: (caseId: string, formData: FormData) =>
    apiClient.post<{ case_id: string; source_format: string; artifacts_created: number; artifact_ids: string[]; kafka_event_id: string }>(
      `/cases/${caseId}/ingest`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    ).then(res => res.data),
  getAuditLog: (caseId: string) => apiClient.get<T.IngestionAuditLog[]>(`/cases/${caseId}/ingestion-audit`).then(res => res.data),
};

// Graph API
export const graphApi = {
  createPerson: (caseId: string, data: { display_name: string; role: string; classification_tag?: T.ClassificationTag }) =>
    apiClient.post<T.GraphNode>(`/cases/${caseId}/graph/person`, data).then(res => res.data),
  getPerson: (caseId: string, nodeId: string) => apiClient.get<T.GraphNode>(`/cases/${caseId}/graph/person/${nodeId}`).then(res => res.data),
  
  createDevice: (caseId: string, data: { device_type: string; identifiers: string[]; classification_tag?: T.ClassificationTag }) =>
    apiClient.post<T.GraphNode>(`/cases/${caseId}/graph/device`, data).then(res => res.data),
  getDevice: (caseId: string, nodeId: string) => apiClient.get<T.GraphNode>(`/cases/${caseId}/graph/device/${nodeId}`).then(res => res.data),
  
  createAccount: (caseId: string, data: { account_type: string; platform: string; classification_tag?: T.ClassificationTag }) =>
    apiClient.post<T.GraphNode>(`/cases/${caseId}/graph/account`, data).then(res => res.data),
  getAccount: (caseId: string, nodeId: string) => apiClient.get<T.GraphNode>(`/cases/${caseId}/graph/account/${nodeId}`).then(res => res.data),

  createLocation: (caseId: string, data: { location_type: string; coordinates?: string; address?: string; classification_tag?: T.ClassificationTag }) =>
    apiClient.post<T.GraphNode>(`/cases/${caseId}/graph/location`, data).then(res => res.data),
  getLocation: (caseId: string, nodeId: string) => apiClient.get<T.GraphNode>(`/cases/${caseId}/graph/location/${nodeId}`).then(res => res.data),

  createOrganization: (caseId: string, data: { org_type: string; name: string; classification_tag?: T.ClassificationTag }) =>
    apiClient.post<T.GraphNode>(`/cases/${caseId}/graph/organization`, data).then(res => res.data),
  getOrganization: (caseId: string, nodeId: string) => apiClient.get<T.GraphNode>(`/cases/${caseId}/graph/organization/${nodeId}`).then(res => res.data),

  createEvent: (caseId: string, data: { event_type: string; valid_from?: string; valid_to?: string; confidence?: number; artifact_id?: string; classification_tag?: T.ClassificationTag }) =>
    apiClient.post<T.GraphNode>(`/cases/${caseId}/graph/event`, data).then(res => res.data),
  getEvent: (caseId: string, nodeId: string) => apiClient.get<T.GraphNode>(`/cases/${caseId}/graph/event/${nodeId}`).then(res => res.data),

  createRelationship: (caseId: string, data: T.GraphEdge) =>
    apiClient.post<T.GraphEdge>(`/cases/${caseId}/graph/relationships`, data).then(res => res.data),
  getNeighbors: (caseId: string, nodeId: string) => apiClient.get<T.NeighborResponse[]>(`/cases/${caseId}/graph/entity/${nodeId}/neighbors`).then(res => res.data),
  getSummary: (caseId: string) => apiClient.get<T.GraphSummary>(`/cases/${caseId}/graph/summary`).then(res => res.data),
  getTimeline: (caseId: string, from: string, to: string) =>
    apiClient.get<T.TimelineEvent[]>(`/cases/${caseId}/graph/timeline`, { params: { from, to } }).then(res => res.data),
};

// Identity API
export const identityApi = {
  createFacet: (caseId: string, data: { facet_type: string; value: string; person_id?: string; classification_tag?: T.ClassificationTag }) =>
    apiClient.post<any>(`/cases/${caseId}/graph/identity-facet`, data).then(res => res.data),
  listIdentifiers: (caseId: string, personId: string) =>
    apiClient.get<any[]>(`/cases/${caseId}/graph/person/${personId}/identifiers`).then(res => res.data),
  mergePersons: (caseId: string, data: { person_id_keep: string; person_id_merge: string; reason?: string }) =>
    apiClient.post<any>(`/cases/${caseId}/graph/merge-persons`, data).then(res => res.data),
};

// Reasoning API (Hypothesis, Assumption, Contradiction, EvidenceGap)
export const reasoningApi = {
  listHypotheses: (caseId: string) => apiClient.get<T.Hypothesis[]>(`/cases/${caseId}/hypotheses`).then(res => res.data),
  getHypothesis: (caseId: string, id: string) => apiClient.get<T.Hypothesis>(`/cases/${caseId}/hypotheses/${id}`).then(res => res.data),
  createHypothesis: (caseId: string, data: any) => apiClient.post<T.Hypothesis>(`/cases/${caseId}/hypotheses`, data).then(res => res.data),
  updatePredicates: (caseId: string, id: string, predicates: string[]) =>
    apiClient.put<any>(`/cases/${caseId}/hypotheses/${id}/predicates`, { predicates }).then(res => res.data),
  getImpliedEvidenceStatus: (caseId: string, id: string) =>
    apiClient.get<any>(`/cases/${caseId}/hypotheses/${id}/implied-evidence-status`).then(res => res.data),
  spawnHypothesis: (caseId: string, data: { narrative: string; predicates?: string[]; scenario_type?: string }) =>
    apiClient.post<any>(`/cases/${caseId}/hypotheses/spawn`, data).then(res => res.data),
  eliminateHypothesis: (caseId: string, id: string, data: { evidence_id: string; reasoning: string }) =>
    apiClient.post<any>(`/cases/${caseId}/hypotheses/${id}/eliminate`, data).then(res => res.data),
  explainHypothesis: (caseId: string, id: string) => apiClient.get<any>(`/cases/${caseId}/hypotheses/${id}/explain`).then(res => res.data),
  getRankedHypotheses: (caseId: string) => apiClient.get<any[]>(`/cases/${caseId}/hypotheses/ranked`).then(res => res.data),
  getSensitivity: (caseId: string, id: string) => apiClient.get<any[]>(`/cases/${caseId}/hypotheses/${id}/sensitivity`).then(res => res.data),
  getChallenge: (caseId: string, id: string) => apiClient.get<any>(`/cases/${caseId}/hypotheses/${id}/challenge`).then(res => res.data),
  
  // Assumptions
  listAssumptions: (caseId: string) => apiClient.get<T.Assumption[]>(`/cases/${caseId}/assumptions`).then(res => res.data),
  createAssumption: (caseId: string, data: any) => apiClient.post<T.Assumption>(`/cases/${caseId}/assumptions`, data).then(res => res.data),
  
  // Contradictions
  listContradictions: (caseId: string) => apiClient.get<T.Contradiction[]>(`/cases/${caseId}/contradictions`).then(res => res.data),
  createContradiction: (caseId: string, data: any) => apiClient.post<T.Contradiction>(`/cases/${caseId}/contradictions`, data).then(res => res.data),
  linkInvolvedNode: (caseId: string, contradictionId: string, targetNodeId: string) =>
    apiClient.post<any>(`/cases/${caseId}/contradictions/${contradictionId}/involves`, { target_node_id: targetNodeId }).then(res => res.data),

  // Evidence Gaps
  listEvidenceGaps: (caseId: string) => apiClient.get<T.EvidenceGap[]>(`/cases/${caseId}/evidence-gaps`).then(res => res.data),
  createEvidenceGap: (caseId: string, data: any) => apiClient.post<T.EvidenceGap>(`/cases/${caseId}/evidence-gaps`, data).then(res => res.data),
  linkRelatedNode: (caseId: string, gapId: string, targetNodeId: string) =>
    apiClient.post<any>(`/cases/${caseId}/evidence-gaps/${gapId}/relates-to`, { target_node_id: targetNodeId }).then(res => res.data),

  // Causal
  createCausalLink: (caseId: string, data: { cause_event_id: string; effect_event_id: string; mechanism: string; confidence?: number; evidence_basis?: string[] }) =>
    apiClient.post<any>(`/cases/${caseId}/graph/causal-link`, data).then(res => res.data),
  getCausalChain: (caseId: string, focalEventId: string) =>
    apiClient.get<any>(`/cases/${caseId}/reasoning/causal-chain/${focalEventId}`).then(res => res.data),
  counterfactualSimulation: (caseId: string, data: { focal_event_id: string; removed_event_id: string; actor?: string }) =>
    apiClient.post<any>(`/cases/${caseId}/reasoning/counterfactual`, data).then(res => res.data),

  // Probabilistic
  getConfidenceReport: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/reasoning/confidence-report`).then(res => res.data),
  updateAbsenceRates: (data: { evidence_type: string; p_gen_innocent: number; p_gen_guilty: number }) =>
    apiClient.put<any>('/config/absence-base-rates', data).then(res => res.data),

  // Crime Twin
  getCrimeTwin: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/crime-twin`).then(res => res.data),
  simulateScenario: (caseId: string, data: { hypothesis_id: string; modifications: any[] }) =>
    apiClient.post<any>(`/cases/${caseId}/crime-twin/simulate`, data).then(res => res.data),

  // ORACLE
  getOracleReport: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/oracle/report`).then(res => res.data),
  getOracleHistory: (caseId: string) => apiClient.get<any[]>(`/cases/${caseId}/oracle/history`).then(res => res.data),

  // AIRE
  getAireStatus: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/aire/status`).then(res => res.data),
  triggerAireProcess: (caseId: string, data: { event_type: string; node_id?: string; node_type?: string; relationship_type?: string; touched_entities?: string[] }) =>
    apiClient.post<any>(`/cases/${caseId}/aire/process`, data).then(res => res.data),
  deadEndPredict: (caseId: string, actionType: string, targetRef?: string) =>
    apiClient.get<any>(`/cases/${caseId}/aire/dead-end-predict`, { params: { action_type: actionType, target_ref: targetRef } }).then(res => res.data),
};

// Intelligence API (Heatmap, Contradictions, Gaps, Actions)
export const intelligenceApi = {
  getAttentionHeatmap: (caseId: string) => apiClient.get<any[]>(`/cases/${caseId}/attention-heatmap`).then(res => res.data),
  getAttentionChanges: (caseId: string, since: string) =>
    apiClient.get<any[]>(`/cases/${caseId}/attention-heatmap/changes`, { params: { since } }).then(res => res.data),
  
  listActionQueue: (caseId: string, status?: string) =>
    apiClient.get<T.InvestigationAction[]>(`/cases/${caseId}/action-queue`, { params: { status } }).then(res => res.data),
  updateActionStatus: (caseId: string, actionId: string, data: { new_status: string; dismissal_reason?: string }) =>
    apiClient.post<any>(`/cases/${caseId}/action-queue/${actionId}/status`, data).then(res => res.data),
  getActionStats: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/action-queue/stats`).then(res => res.data),

  runContradictionScan: (caseId: string) => apiClient.post<any>(`/cases/${caseId}/contradictions/scan`).then(res => res.data),
  getContradictionsDetail: (caseId: string) => apiClient.get<any[]>(`/cases/${caseId}/contradictions/detail`).then(res => res.data),
  runGapScan: (caseId: string) => apiClient.post<any>(`/cases/${caseId}/evidence-gaps/scan`).then(res => res.data),
  resolveEvidenceGap: (caseId: string, gapId: string, resolutionNote: string) =>
    apiClient.post<any>(`/cases/${caseId}/evidence-gaps/${gapId}/resolve`, { resolution_note: resolutionNote }).then(res => res.data),
  getEvidenceGapsDetail: (caseId: string) => apiClient.get<T.EvidenceGap[]>(`/cases/${caseId}/evidence-gaps/detail`).then(res => res.data),
};

// Behavioral API
export const behavioralApi = {
  computeBaseline: (caseId: string, personId: string, minEvents?: number) =>
    apiClient.post<T.BehavioralBaseline>(`/cases/${caseId}/graph/person/${personId}/baseline/compute`, null, { params: { min_events: minEvents } }).then(res => res.data),
  scanAnomalies: (caseId: string, personId: string, from: string, to: string, zThreshold?: number) =>
    apiClient.post<T.BehavioralAnomaly[]>(`/cases/${caseId}/graph/person/${personId}/anomalies/scan`, null, { params: { from, to, z_threshold: zThreshold } }).then(res => res.data),
};

// Deception API
export const deceptionApi = {
  assessDeception: (caseId: string, data: { artifact_id?: string; osint_record_id?: string; content_type?: string }) =>
    apiClient.post<T.DeceptionAssessment>(`/cases/${caseId}/deception/assess`, data).then(res => res.data),
};

// Legal Intelligence API
export const legalApi = {
  mapElements: (caseId: string, threshold?: number) =>
    apiClient.post<any>(`/cases/${caseId}/legal/map-elements`, { threshold }).then(res => res.data),
  getElementMap: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/legal/element-map`).then(res => res.data),
  getEvidenceLawMap: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/legal/evidence-law-map`).then(res => res.data),
  confirmMapping: (caseId: string, mappingId: string) =>
    apiClient.post<any>(`/cases/${caseId}/legal/element-map/${mappingId}/confirm`).then(res => res.data),
  rejectMapping: (caseId: string, mappingId: string, reason: string) =>
    apiClient.post<any>(`/cases/${caseId}/legal/element-map/${mappingId}/reject`, { rejection_reason: reason }).then(res => res.data),
  
  qualifySections: (caseId: string) => apiClient.post<any>(`/cases/${caseId}/legal/qualify`).then(res => res.data),
  getRecommendedSections: (caseId: string) => apiClient.get<T.LegalQualification[]>(`/cases/${caseId}/legal/recommended-sections`).then(res => res.data),
  setQualificationStatus: (caseId: string, qualId: string, status: string) =>
    apiClient.post<any>(`/cases/${caseId}/legal/qualifications/${qualId}/set-status`, { status }).then(res => res.data),
  
  createSufficiencyReport: (caseId: string, sectionId: string) =>
    apiClient.post<T.SufficiencyReport>(`/cases/${caseId}/legal/sufficiency-report/${sectionId}`).then(res => res.data),
  getSufficiencyReport: (caseId: string, sectionId: string) =>
    apiClient.get<T.SufficiencyReport>(`/cases/${caseId}/legal/sufficiency-report/${sectionId}`).then(res => res.data),
  
  scanCompliance: (caseId: string) => apiClient.post<any>(`/cases/${caseId}/legal/compliance/scan`).then(res => res.data),
  getComplianceReport: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/legal/compliance/report`).then(res => res.data),
  getProceduralTimeline: (caseId: string) => apiClient.get<any[]>(`/cases/${caseId}/legal/procedural-timeline`).then(res => res.data),
  confirmCompliance: (caseId: string, requirementId: string, notes: string) =>
    apiClient.post<any>(`/cases/${caseId}/legal/compliance/${requirementId}/confirm`, { confirmation_notes: notes }).then(res => res.data),
  
  generateChargesheetReadiness: (caseId: string) => apiClient.post<T.ChargesheetReadiness>(`/cases/${caseId}/legal/chargesheet-readiness`).then(res => res.data),
  getChargesheetReadiness: (caseId: string) => apiClient.get<T.ChargesheetReadiness>(`/cases/${caseId}/legal/chargesheet-readiness`).then(res => res.data),
  getChargesheetReadinessHistory: (caseId: string) =>
    apiClient.get<any[]>(`/cases/${caseId}/legal/chargesheet-readiness/history`).then(res => res.data),
  
  getLegalRecommendations: (caseId: string) => apiClient.get<T.LegalRecommendation[]>(`/cases/${caseId}/legal/recommendations`).then(res => res.data),
  getEvidenceStrengthMatrix: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/legal/evidence-strength-matrix`).then(res => res.data),
  getComplianceAlerts: (caseId: string) => apiClient.get<T.ComplianceAlert[]>(`/cases/${caseId}/legal/compliance/alerts`).then(res => res.data),
  getReasoningTraces: (caseId: string, source?: string, limit?: number) =>
    apiClient.get<T.ReasoningTrace[]>(`/cases/${caseId}/legal/reasoning-traces`, { params: { engine_source: source, limit } }).then(res => res.data),
  getFullAnalysis: (caseId: string) => apiClient.post<any>(`/cases/${caseId}/legal/full-analysis`).then(res => res.data),
};

// Court Intelligence API
export const courtApi = {
  runDefenseSimulation: (caseId: string, categories?: string[]) =>
    apiClient.post<any>(`/cases/${caseId}/court/defense-simulation`, { categories }).then(res => res.data),
  getLatestSimulation: (caseId: string) =>
    apiClient.get<any>(`/cases/${caseId}/court/defense-simulation/latest`).then(res => res.data),
  
  runIntegrityAudit: (caseId: string) => apiClient.post<any>(`/cases/${caseId}/court/integrity-audit`).then(res => res.data),
  getIntegrityAudit: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/court/integrity-audit`).then(res => res.data),
  getArtifactCertificate: (artifactId: string) =>
    apiClient.get<any>(`/evidence/${artifactId}/integrity-certificate`).then(res => res.data),
  getWeakArtifacts: (caseId: string) => apiClient.get<any[]>(`/cases/${caseId}/court/integrity-audit/weak`).then(res => res.data),

  runCourtReadiness: (caseId: string) => apiClient.post<any>(`/cases/${caseId}/court/readiness`).then(res => res.data),
  getCourtReadiness: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/court/readiness`).then(res => res.data),
  getChecklist: (caseId: string) => apiClient.get<any[]>(`/cases/${caseId}/court/readiness/checklist`).then(res => res.data),

  createProsecutionNarrative: (caseId: string) => apiClient.post<any>(`/cases/${caseId}/court/prosecution-narrative`).then(res => res.data),
  getExpertPrepGuide: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/court/expert-preparation`).then(res => res.data),
  getCounterNarratives: (caseId: string) => apiClient.get<any[]>(`/cases/${caseId}/court/counter-narratives`).then(res => res.data),

  runConvictionRisk: (caseId: string) => apiClient.post<any>(`/cases/${caseId}/court/conviction-risk`).then(res => res.data),
  getConvictionRisk: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/court/conviction-risk`).then(res => res.data),
};

// Cross Case API
export const crossCaseApi = {
  getSimilarCases: (caseId: string) => apiClient.get<any[]>(`/cases/${caseId}/cross-case/similar`).then(res => res.data),
  getRecommendedPlaybook: (caseId: string) => apiClient.get<any>(`/cases/${caseId}/cross-case/recommended-playbook`).then(res => res.data),
  getPlaybooksReference: (crimeCategoryId: string) => apiClient.get<any[]>(`/reference/playbooks/${crimeCategoryId}`).then(res => res.data),
  completePlaybookStep: (caseId: string, stepNumber: number) =>
    apiClient.post<any>(`/cases/${caseId}/cross-case/playbook-step/${stepNumber}/complete`).then(res => res.data),
  runCorpusExtractionAll: () => apiClient.post<any>('/admin/corpus/extract-all').then(res => res.data),
  runCorpusExtractionCase: (caseId: string) => apiClient.post<any>(`/admin/corpus/extract/${caseId}`).then(res => res.data),
  fingerprintPerson: (caseId: string, personId: string) =>
    apiClient.post<any>(`/cases/${caseId}/cross-case/fingerprint/${personId}`).then(res => res.data),
};

// National Scale API
export const nationalApi = {
  getThreatSignals: () => apiClient.get<any[]>('/national/threat-signals').then(res => res.data),
  getIntelligenceDashboard: () => apiClient.get<any>('/national/intelligence-dashboard').then(res => res.data),
  detectThreatSignals: () => apiClient.post<any>('/national/threat-signals/detect').then(res => res.data),
  createAdvisory: (signalId: string, data: any) => apiClient.post<any>(`/national/threat-signals/${signalId}/advisory`, data).then(res => res.data),
  
  getDeconflictionAlerts: (caseId: string) => apiClient.get<any[]>(`/cases/${caseId}/national/deconfliction-alerts`).then(res => res.data),
  acknowledgeDeconflictionAlert: (alertId: string) => apiClient.post<any>(`/national/deconfliction-alerts/${alertId}/acknowledge`).then(res => res.data),
  indexDeconfliction: () => apiClient.post<any>('/national/deconfliction/index').then(res => res.data),
  
  getAgencies: () => apiClient.get<any[]>('/admin/agencies').then(res => res.data),
  createAgency: (data: any) => apiClient.post<any>('/admin/agencies', data).then(res => res.data),
  createInvestigator: (agencyId: string, data: any) =>
    apiClient.post<any>(`/admin/agencies/${agencyId}/investigators`, data).then(res => res.data),
  getPlatformHealth: () => apiClient.get<any>('/admin/platform-health').then(res => res.data),
  getArchivalCandidates: () => apiClient.get<any[]>('/admin/archival-candidates').then(res => res.data),
  archiveCase: (caseId: string) => apiClient.post<any>(`/admin/archive/${caseId}`).then(res => res.data),
};

// Reference API
export const referenceApi = {
  getCrimeCategories: () => apiClient.get<any[]>('/crime-categories').then(res => res.data),
  getCrimeCategory: (id: string) => apiClient.get<any>(`/crime-categories/${id}`).then(res => res.data),
  getCrimeCategoryLegalSections: (id: string) => apiClient.get<any[]>(`/crime-categories/${id}/legal-sections`).then(res => res.data),
  getLegalSection: (id: string) => apiClient.get<any>(`/legal-sections/${id}`).then(res => res.data),
  classifyCase: (caseId: string, crimeCategoryIds: string[]) =>
    apiClient.post<any>(`/cases/${caseId}/classify`, { crime_category_ids: crimeCategoryIds }).then(res => res.data),
};

// Copilot API
export const copilotApi = {
  query: (caseId: string, query: string, context?: any) =>
    apiClient.post<{
      intent: string;
      confidence: number;
      response_md: string;
      entities_referenced: string[];
      suggested_actions: string[];
      query_time_ms: number;
    }>(`/cases/${caseId}/copilot/query`, { query, context }).then(res => res.data),
  getIntents: (caseId: string) =>
    apiClient.get<any>(`/cases/${caseId}/copilot/intents`).then(res => res.data),
};

// Simulation API
export const simulationApi = {
  simulate: (data: {
    scenario: string;
    suspects?: number;
    timeline_days?: number;
    contradiction_density?: string;
    seed?: number;
  }) => apiClient.post<{
    case_id: string;
    scenario: string;
    suspects_created: number;
    artifacts_created: number;
    events_created: number;
    contradictions_planted: number;
    summary_md: string;
    download_url: string;
  }>('/cases/simulate', data).then(res => res.data),
  getScenarios: () =>
    apiClient.get<any>('/simulation/scenarios').then(res => res.data),
  downloadZip: (caseId: string) =>
    apiClient.get(`/cases/${caseId}/simulate/download`, { responseType: 'blob' }).then(res => res.data),
};

// AI Models API (Gap 3)
export const aiModelsApi = {
  extractEntities: (text: string) =>
    apiClient.post<any>('/ai/ner', { text }).then(res => res.data),
  analyzeSentiment: (text: string) =>
    apiClient.post<any>('/ai/sentiment', { text }).then(res => res.data),
  classifyIntent: (text: string) =>
    apiClient.post<any>('/ai/intent', { text }).then(res => res.data),
  analyzeStylometry: (text: string) =>
    apiClient.post<any>('/ai/stylometry', { text }).then(res => res.data),
  compareAuthorship: (textA: string, textB: string) =>
    apiClient.post<any>('/ai/stylometry/compare', { text_a: textA, text_b: textB }).then(res => res.data),
  scoreDeception: (text: string) =>
    apiClient.post<any>('/ai/deception', { text }).then(res => res.data),
  matchEntities: (entityA: any, entityB: any, threshold?: number) =>
    apiClient.post<any>('/ai/entity-match', { entity_a: entityA, entity_b: entityB, threshold }).then(res => res.data),
  getModelRegistry: () =>
    apiClient.get<any>('/ai/models').then(res => res.data),
};

// Acquisition API (Gap 4 + 18)
export const acquisitionApi = {
  detectDevices: () =>
    apiClient.get<any>('/acquisition/devices').then(res => res.data),
  createJob: (data: any) =>
    apiClient.post<any>('/acquisition/jobs', data).then(res => res.data),
  startJob: (jobId: string) =>
    apiClient.post<any>(`/acquisition/jobs/${jobId}/start`).then(res => res.data),
  registerEquipment: (data: any) =>
    apiClient.post<any>('/acquisition/equipment', data).then(res => res.data),
  getInventory: () =>
    apiClient.get<any>('/acquisition/inventory').then(res => res.data),
};

// Enhanced OSINT API (Gap 5)
export const osintDeepApi = {
  runDeepOsint: (query: string, queryType?: string) =>
    apiClient.post<any>('/osint/deep', { query, query_type: queryType || 'auto' }).then(res => res.data),
  traceBlockchain: (wallet: string, maxHops?: number) =>
    apiClient.post<any>('/osint/blockchain/trace', { wallet, max_hops: maxHops || 2 }).then(res => res.data),
  analyzeSocialGraph: (communications: any[]) =>
    apiClient.post<any>('/osint/social-graph', { communications }).then(res => res.data),
};

// Digital Twin API (Gap 6)
export const digitalTwinApi = {
  findSharedEntities: (entityType?: string, limit?: number) =>
    apiClient.get<any>('/digital-twin/shared-entities', { params: { entity_type: entityType, limit } }).then(res => res.data),
  getCrossCaseLinks: (caseId: string) =>
    apiClient.get<any>(`/digital-twin/cross-case-links/${caseId}`).then(res => res.data),
};

// Predictive Intelligence API (Gap 7 + 16)
export const predictiveApi = {
  predictSuspect: (caseId: string, suspectId: string) =>
    apiClient.get<any>(`/cases/${caseId}/predict/suspect/${suspectId}`).then(res => res.data),
  evidenceExpiration: (caseId: string) =>
    apiClient.get<any>(`/cases/${caseId}/predict/evidence-expiration`).then(res => res.data),
  witnessPriority: (caseId: string) =>
    apiClient.get<any>(`/cases/${caseId}/predict/witness-priority`).then(res => res.data),
  seizurePriority: (caseId: string) =>
    apiClient.get<any>(`/cases/${caseId}/predict/seizure-priority`).then(res => res.data),
  simulateAction: (caseId: string, actionType: string, targetId: string) =>
    apiClient.post<any>(`/cases/${caseId}/simulate-action`, { action_type: actionType, target_id: targetId }).then(res => res.data),
};

// Multi-Agent AI API (Gap 8)
export const agentsApi = {
  runAnalysis: (caseId: string) =>
    apiClient.post<any>(`/cases/${caseId}/agents/analyze`, {}).then(res => res.data),
};

// Explainability API (Gap 11)
export const explainApi = {
  explainHypothesis: (caseId: string, hypothesisId: string) =>
    apiClient.get<any>(`/cases/${caseId}/explain/hypothesis/${hypothesisId}`).then(res => res.data),
  explainCourtReadiness: (caseId: string) =>
    apiClient.get<any>(`/cases/${caseId}/explain/court-readiness`).then(res => res.data),
  explainContradiction: (caseId: string, contradictionId: string) =>
    apiClient.get<any>(`/cases/${caseId}/explain/contradiction/${contradictionId}`).then(res => res.data),
};

// Learning System API (Gap 12)
export const learningApi = {
  submitFeedback: (data: any) =>
    apiClient.post<any>('/learning/feedback', data).then(res => res.data),
  recordOutcome: (data: any) =>
    apiClient.post<any>('/learning/case-outcome', data).then(res => res.data),
  getAnalytics: () =>
    apiClient.get<any>('/learning/analytics').then(res => res.data),
  getWeights: () =>
    apiClient.get<any>('/learning/weights').then(res => res.data),
};

// Federation API (Gap 13)
export const federationApi = {
  anonymousLinkCheck: (hashedIdentifiers: string[], agencyId: string) =>
    apiClient.post<any>('/federation/anonymous-link-check', { hashed_identifiers: hashedIdentifiers, agency_id: agencyId }).then(res => res.data),
};

// Streaming API (Gap 14)
export const streamingApi = {
  getStatus: () =>
    apiClient.get<any>('/streaming/status').then(res => res.data),
  subscribe: (caseId: string, alertTypes?: string[]) =>
    apiClient.post<any>('/streaming/subscribe', { case_id: caseId, alert_types: alertTypes || ['all'] }).then(res => res.data),
};
