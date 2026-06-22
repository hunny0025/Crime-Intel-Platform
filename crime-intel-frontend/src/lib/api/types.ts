export type CaseStatus =
  | 'open'
  | 'under_investigation'
  | 'closed'
  | 'closed_convicted'
  | 'closed_acquitted'
  | 'closed_insufficient_evidence'
  | 'closed_other';

export type ClassificationTag =
  | 'public_osint'
  | 'case_sensitive'
  | 'pii'
  | 'evidentiary'
  | 'legal_privileged';

export interface Case {
  case_id: string;
  case_type: string;
  status: CaseStatus;
  classification_tag: ClassificationTag;
  created_at: string;
  updated_at: string;
  created_by: string;
}

export interface CaseEntity {
  id: string;
  case_id: string;
  entity_id: string;
  entity_type: string;
  role: string;
}

export interface ChainOfCustodyLog {
  action: string;
  actor: string;
  timestamp: string;
  notes?: string;
  signature?: string;
}

export interface EvidenceArtifact {
  artifact_id: string;
  case_id: string;
  source_tool: string;
  source_device_id: string | null;
  collection_timestamp_utc: string;
  original_timezone: string;
  content_hash: string;
  previous_record_hash: string | null;
  record_hash: string;
  content_pointer: string;
  classification_tag: ClassificationTag;
  chain_of_custody_log: ChainOfCustodyLog[];
  created_at: string;
}

export interface IngestionAuditLog {
  audit_id: string;
  case_id: string;
  actor: string;
  source_format: string;
  num_artifacts: number;
  timestamp: string;
  kafka_event_id: string;
}

export interface IngestionAuditResponse {
  total: number;
  page: number;
  page_size: number;
  records: IngestionAuditLog[];
}

export interface GraphNode {
  id: string;
  case_id: string;
  classification_tag: ClassificationTag;
  created_at: string;
  label: string; // Person, Device, Account, Location, Organization, Event, Hypothesis, Contradiction, EvidenceGap, etc.
  display_name?: string;
  role?: string;
  device_type?: string;
  identifiers?: string[];
  account_type?: string;
  platform?: string;
  location_type?: string;
  coordinates?: string;
  address?: string;
  org_type?: string;
  name?: string;
  event_type?: string;
  valid_from?: string;
  valid_to?: string;
  confidence?: number;
  artifact_id?: string;
  narrative?: string;
  probability?: number;
  confidence_in_probability?: number;
  status?: string;
  description?: string;
  severity?: 'low' | 'medium' | 'high';
  contradiction_type?: string;
  expected_value?: 'low' | 'medium' | 'high';
  urgency?: 'low' | 'medium' | 'high';
  [key: string]: any;
}

export interface GraphEdge {
  from_node_id: string;
  to_node_id: string;
  relationship_type: string;
  valid_from?: string;
  valid_to?: string;
  confidence?: number;
  evidence_basis: string[];
}

export interface GraphSummary {
  node_counts: Record<string, number>;
  relationship_counts: Record<string, number>;
  unprocessed_file_artifacts: number;
}

export interface TimelineEvent {
  event: GraphNode;
  connected_entities: GraphNode[];
  confidence: number | null;
  evidence_basis: string[];
}

export interface Hypothesis extends GraphNode {
  predicates?: string[];
  implied_evidence?: string[];
  forbidden_evidence?: string[];
}

export interface Assumption extends GraphNode {
  statement: string;
  criticality: 'low' | 'medium' | 'high';
  verification_status: 'unverified' | 'verified' | 'contradicted';
}

export interface Contradiction extends GraphNode {
  description: string;
  severity: 'low' | 'medium' | 'high';
  contradiction_type: string;
  detected_at: string;
  involved_entities?: GraphNode[];
}

export interface EvidenceGap extends GraphNode {
  description: string;
  expected_value: 'low' | 'medium' | 'high';
  urgency: 'low' | 'medium' | 'high';
  status: 'open' | 'resolved';
  related_entities?: any[];
}

export interface OSINTRecord {
  record_id: string;
  case_id: string;
  source_type: string;
  query: string;
  retrieved_at: string;
  raw_result: any;
  extracted_entities: any[] | null;
  classification_tag: ClassificationTag;
}

export interface OSINTResponse {
  total: number;
  page: number;
  page_size: number;
  records: OSINTRecord[];
}

export interface DeceptionAssessment {
  assessment_id: string;
  target_type: 'evidence_artifact' | 'osint_record';
  target_id: string;
  deception_score: number;
  confidence: number;
  model_name: string;
  explanation: string;
}

export interface BehavioralBaseline {
  id: string;
  case_id: string;
  person_id: string;
  event_type_frequencies: Record<string, number>;
  average_event_interval_hours: number;
  created_at: string;
}

export interface BehavioralAnomaly {
  id: string;
  case_id: string;
  person_id: string;
  anomaly_type: string;
  severity: 'low' | 'medium' | 'high';
  description: string;
  statistical_basis: string;
  time_window: string;
}

export interface LegalMapping {
  id: string;
  case_id: string;
  element_id: string;
  artifact_id: string;
  confidence: number;
  status: 'pending' | 'confirmed' | 'rejected';
  rejection_reason?: string;
  mapped_at: string;
}

export interface LegalQualification {
  id: string;
  case_id: string;
  section_id: string;
  qualification_status: 'applicable' | 'not_applicable' | 'pending';
  confidence_level: number;
  supporting_reasons: string[];
  missing_elements: {
    element_id: string;
    description: string;
    suggested_actions: string[];
  }[];
  judicial_interpretation?: string;
  updated_at: string;
}

export interface SufficiencyReport {
  id: string;
  case_id: string;
  section_id: string;
  is_sufficient: boolean;
  score: number;
  element_status: Record<string, 'proven' | 'partially_proven' | 'unproven'>;
  analysis_text: string;
  generated_at: string;
}

export interface ComplianceAlert {
  id: string;
  requirement_id: string;
  milestone_name: string;
  status: 'pending' | 'due_soon' | 'overdue' | 'compliant' | 'non_compliant';
  deadline_utc?: string;
  time_left_hours?: number;
  alert_severity: 'low' | 'medium' | 'high';
}

export interface ChargesheetReadiness {
  id: string;
  case_id: string;
  overall_readiness_score: number;
  readiness_tier: 'Ready' | 'Caution' | 'Insufficient';
  element_readiness_percentage: number;
  procedural_compliance_percentage: number;
  unsupported_allegations: string[];
  history?: { timestamp: string; score: number }[];
  evaluated_at: string;
}

export interface LegalRecommendation {
  id: string;
  category: 'highest_value' | 'compliance_fix' | 'sufficiency_gap' | 'general';
  action_description: string;
  expected_value: number;
  reasoning: string;
}

export interface ReasoningTrace {
  id: string;
  case_id: string;
  engine_source: string;
  input_event_type: string;
  steps_completed: string[];
  reasoning_output: string;
  timestamp: string;
}

export interface InvestigationAction {
  action_id: string;
  case_id: string;
  action_type: 'review_contradiction' | 'pursue_evidence_gap' | 'review_high_attention_entity';
  target_ref: string;
  target_summary?: string;
  priority_score: number;
  status: 'pending' | 'in_progress' | 'done' | 'dismissed';
  created_at: string;
  status_updated_at: string;
  dismissal_reason?: string;
}

export interface NeighborResponse {
  node: Record<string, any>;
  relationship: Record<string, any>;
}

