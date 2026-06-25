const http = require('http');

const PORT = 8000;

const cases = [
  {
    case_id: "CASE-2026-001",
    case_type: "Cyber Espionage",
    status: "open",
    classification_tag: "case_sensitive",
    created_by: "investigator_alpha",
    created_at: "2026-06-20T00:00:00Z",
    updated_at: "2026-06-24T00:00:00Z"
  },
  {
    case_id: "CASE-2026-002",
    case_type: "Ransomware Attack",
    status: "under_investigation",
    classification_tag: "evidentiary",
    created_by: "investigator_beta",
    created_at: "2026-06-21T00:00:00Z",
    updated_at: "2026-06-24T00:00:00Z"
  },
  {
    case_id: "CASE-2026-003",
    case_type: "Financial Crypto Scam",
    status: "open",
    classification_tag: "public_osint",
    created_by: "investigator_gamma",
    created_at: "2026-06-22T00:00:00Z",
    updated_at: "2026-06-24T00:00:00Z"
  }
];

const threatSignals = [
  {
    threat_type: "DDoS Threat",
    description: "Anomalous ingress spike detected targeting critical power grid subnet.",
    anomaly_score: 0.94,
    source_system: "NCIIPC-Sensor-Grid",
    detected_at: new Date().toISOString()
  },
  {
    threat_type: "Ransomware Command Activity",
    description: "Exfiltration pattern detected on secondary defense contractor network.",
    anomaly_score: 0.88,
    source_system: "CERT-In-Alerts",
    detected_at: new Date().toISOString()
  }
];

const actionQueue = [
  {
    action_id: "ACT-101",
    title: "Verify Section 65B Electronic Certificate",
    description: "Verify digital signature certificate for raw server logs (Log-042).",
    priority: "high",
    status: "pending",
    created_at: new Date().toISOString()
  },
  {
    action_id: "ACT-102",
    title: "OSINT Lookup for suspected domain",
    description: "Query WHOIS and DNS history for domain 'cbi-portal-verify.in'.",
    priority: "medium",
    status: "pending",
    created_at: new Date().toISOString()
  }
];

const graphSummary = {
  node_counts: {
    Person: 4,
    Device: 8,
    Account: 6,
    Location: 3,
    Organization: 2,
    Event: 14,
    EvidenceArtifact: 12,
    Hypothesis: 3,
    Contradiction: 2,
    IdentityFacet: 9
  },
  relationship_counts: {
    ASSOCIATED_WITH: 15,
    COMMUNICATED_WITH: 24,
    LOCATED_AT: 8,
    OWNER_OF: 10,
    RESOLVED_TO: 9,
    SAME_AS: 4,
    CONTRADICTS: 2,
    SUPPORTED_BY: 6
  }
};

const evidenceArtifacts = [
  {
    artifact_id: "ART-2991",
    name: "Router_Syslogs_June.txt",
    file_path: "evidence/Router_Syslogs_June.txt",
    size_bytes: 140882,
    hash_sha256: "8e3c5a6d2f7e8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c",
    mime_type: "text/plain",
    created_at: "2026-06-23T14:22:00Z",
    has_section_65b: true,
    certificate_hash: "9f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c8e3c5a6d2f7e8b9c0d1e2f3a4b5c6d7e"
  },
  {
    artifact_id: "ART-2992",
    name: "Suspicious_Transaction.json",
    file_path: "evidence/Suspicious_Transaction.json",
    size_bytes: 4096,
    hash_sha256: "3f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8e3c5a6d2f7e8b9c0d1e2f3a4b5c6d7e",
    mime_type: "application/json",
    created_at: "2026-06-23T15:10:00Z",
    has_section_65b: false,
    certificate_hash: null
  }
];

const ingestionLogs = [
  {
    audit_id: "AUD-001",
    case_id: "CASE-2026-001",
    source_format: "Syslog Router Dump",
    actor: "investigator_alpha",
    num_artifacts: 2,
    kafka_event_id: "evt_9918a-bb21-4f90",
    timestamp: "2026-06-23T14:25:00Z"
  }
];

const complianceReport = {
  case_id: "CASE-2026-001",
  compliance_score: 85,
  compliance_alerts: [
    {
      requirement_id: "REQ-BSA-65B",
      requirement_name: "BSA Section 65B Electronic Certificate",
      status: "warning",
      notes: "Artifact 'Suspicious_Transaction.json' is missing a Section 65B certificate."
    },
    {
      requirement_id: "REQ-BNSS-173",
      requirement_name: "BNSS Section 173 Preliminary Enquiry Window",
      status: "compliant",
      notes: "Enquiry completed within the mandatory 14-day window."
    }
  ],
  checklist: [
    { requirement_id: "REQ-1", name: "FIR Registration", status: "completed" },
    { requirement_id: "REQ-2", name: "Chain of Custody Logs", status: "completed" },
    { requirement_id: "REQ-BSA-65B", name: "BSA Section 65B electronic signature", status: "pending" }
  ]
};

const contradictions = [
  {
    contradiction_id: "CON-001",
    title: "Spatial-Temporal Co-location Conflict",
    description: "Suspect device registered at Cell Tower A (Delhi) and Account login from IP in Mumbai within 3 minutes.",
    severity: "high",
    status: "active",
    created_at: "2026-06-24T12:00:00Z"
  }
];

const gaps = [
  {
    gap_id: "GAP-001",
    title: "Communication Silence Gap",
    description: "Zero packet logs recorded for Target Device 'DEV-881' between June 12 and June 15.",
    severity: "medium",
    status: "open",
    created_at: "2026-06-24T14:00:00Z"
  }
];

const behavioralBaseline = {
  person_id: "node_person_suspect_1",
  event_count: 45,
  activity_density: 0.75,
  normal_hours: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
  anomalies_detected: 2
};

const behavioralAnomalies = [
  {
    anomaly_id: "ANOM-901",
    timestamp: "2026-06-24T03:14:00Z",
    description: "Off-hours data exfiltration query (3:14 AM).",
    z_score: 4.2
  }
];

const legalQualifications = [
  {
    qualification_id: "QUAL-001",
    section: "BSA Section 61",
    description: "Admissibility of electronic records in court.",
    status: "recommended",
    confidence: 0.95
  },
  {
    qualification_id: "QUAL-002",
    section: "IT Act Section 66D",
    description: "Cheating by personation using computer resource.",
    status: "recommended",
    confidence: 0.88
  }
];

const elementMap = {
  offenses: [
    {
      section: "IT Act Section 66D",
      elements_mapped: [
        { element: "Cheating by personation", evidence: "ART-2991", corroboration_level: 0.9 }
      ]
    }
  ]
};

const chargesheetReadiness = {
  readiness_score: 82,
  legal_score: 88,
  integrity_score: 90,
  admissibility_score: 70,
  critical_missing_elements: ["BSA Section 65B Electronic Certificate for ART-2992"]
};

const expertPrepGuide = {
  guidelines: [
    "Verify the hash integrity chain of custody before entering the stand.",
    "Be prepared to explain the 3-minute Delhi-Mumbai spatial contradiction."
  ]
};

const counterNarratives = [
  {
    tactic: "Chain of Custody Challenge",
    defense_narrative: "Evidence artifact Suspicious_Transaction.json has no signature.",
    mitigation: "Present secure log chain on postgres db."
  }
];

const connectedDevices = {
  devices: [
    {
      model: "Seized Crucial 1TB SSD",
      serial: "CRU-9921-SSD",
      interface: "SATA",
      size_gb: 1000,
      device_type: "ssd"
    }
  ]
};

const labInventory = {
  write_blockers: [
    { blocker_id: "BLOCKER-001", name: "Tableau T8u", status: "online" }
  ],
  active_acquisitions: [
    {
      job_id: "JOB-9901-ACQ",
      status: "completed",
      source_device: { model: "Seized Crucial 1TB SSD" },
      method: "physical",
      officer: "investigator_alpha",
      hash_sha256: "8e3c5a6d2f7e8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c"
    }
  ],
  equipment: [
    {
      equipment_id: "EQUIP-881",
      name: "Tableau Forensic Bridge",
      type: "Write Blocker",
      serial_number: "T8U-2026-X99",
      lab_location: "Forensics Room A"
    }
  ]
};

const server = http.createServer((req, res) => {
  // CORS Headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  const url = req.url;
  res.setHeader('Content-Type', 'application/json');

  console.log(`[MOCK] ${req.method} ${url}`);

  if (url === '/cases' && req.method === 'GET') {
    res.writeHead(200);
    res.end(JSON.stringify(cases));
  } else if (url.startsWith('/cases/') && url.endsWith('/graph/summary')) {
    res.writeHead(200);
    res.end(JSON.stringify(graphSummary));
  } else if (url === '/national/threat-signals') {
    res.writeHead(200);
    res.end(JSON.stringify(threatSignals));
  } else if (url.startsWith('/cases/') && url.endsWith('/action-queue')) {
    res.writeHead(200);
    res.end(JSON.stringify(actionQueue));
  } else if (url.startsWith('/cases/') && url.endsWith('/evidence')) {
    res.writeHead(200);
    res.end(JSON.stringify(evidenceArtifacts));
  } else if (url.startsWith('/cases/') && url.endsWith('/ingestion-audit')) {
    res.writeHead(200);
    res.end(JSON.stringify(ingestionLogs));
  } else if (url.startsWith('/cases/') && url.endsWith('/legal/compliance/report')) {
    res.writeHead(200);
    res.end(JSON.stringify(complianceReport));
  } else if (url.startsWith('/cases/') && url.endsWith('/contradictions/detail')) {
    res.writeHead(200);
    res.end(JSON.stringify(contradictions));
  } else if (url.startsWith('/cases/') && url.endsWith('/evidence-gaps/detail')) {
    res.writeHead(200);
    res.end(JSON.stringify(gaps));
  } else if (url.startsWith('/cases/') && url.includes('/baseline/compute')) {
    res.writeHead(200);
    res.end(JSON.stringify(behavioralBaseline));
  } else if (url.startsWith('/cases/') && url.includes('/anomalies/scan')) {
    res.writeHead(200);
    res.end(JSON.stringify(behavioralAnomalies));
  } else if (url.startsWith('/cases/') && url.endsWith('/legal/recommended-sections')) {
    res.writeHead(200);
    res.end(JSON.stringify(legalQualifications));
  } else if (url.startsWith('/cases/') && url.endsWith('/legal/element-map')) {
    res.writeHead(200);
    res.end(JSON.stringify(elementMap));
  } else if (url.startsWith('/cases/') && url.endsWith('/legal/chargesheet-readiness')) {
    res.writeHead(200);
    res.end(JSON.stringify(chargesheetReadiness));
  } else if (url.startsWith('/cases/') && url.endsWith('/court/readiness')) {
    res.writeHead(200);
    res.end(JSON.stringify({ court_ready_score: 85, report: "All chains validated." }));
  } else if (url.startsWith('/cases/') && url.endsWith('/court/integrity-audit')) {
    res.writeHead(200);
    res.end(JSON.stringify({ audit_pass: true, certified_nodes: 12 }));
  } else if (url.startsWith('/cases/') && url.endsWith('/court/expert-preparation')) {
    res.writeHead(200);
    res.end(JSON.stringify(expertPrepGuide));
  } else if (url.startsWith('/cases/') && url.endsWith('/court/counter-narratives')) {
    res.writeHead(200);
    res.end(JSON.stringify(counterNarratives));
  } else if (url === '/acquisition/devices') {
    res.writeHead(200);
    res.end(JSON.stringify(connectedDevices));
  } else if (url === '/acquisition/inventory') {
    res.writeHead(200);
    res.end(JSON.stringify(labInventory));
  } else if (url.startsWith('/cases/') && url.endsWith('/hypotheses')) {
    res.writeHead(200);
    res.end(JSON.stringify([
      { hypothesis_id: "HYP-001", narrative: "Suspect access via compromised API gateway credentials.", status: "active", probability: 0.78 }
    ]));
  } else if (url.startsWith('/cases/') && url.endsWith('/copilot/query')) {
    res.writeHead(200);
    res.end(JSON.stringify({
      intent: "query_evidence",
      confidence: 0.98,
      response_md: "### Analysed Evidence\nWe have analyzed 12 evidence artifacts for **CASE-2026-001**. Key entities resolved include:\n- IP address **192.168.1.105** mapping to Device 'DEV-881'\n- Person **Suspect Alpha** associated with Mumbai logins.",
      entities_referenced: ["Suspect Alpha", "DEV-881"],
      suggested_actions: ["Scan for spatial co-location anomalies", "Verify Section 65B certificates"],
      query_time_ms: 120
    }));
  } else {
    // Catch-all response
    res.writeHead(200);
    res.end(JSON.stringify({ status: "ok", message: "Mock endpoint not explicitly matched", path: url }));
  }
});

server.listen(PORT, () => {
  console.log(`[MOCK BACKEND] Server is running on port ${PORT}`);
});
