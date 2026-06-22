import axios from 'axios';
import * as T from './types';

const OSINT_BASE_URL = process.env.NEXT_PUBLIC_OSINT_URL || 'http://localhost:8001';

export const osintClient = axios.create({
  baseURL: OSINT_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const osintApi = {
  // Records
  listRecords: (caseId: string, params?: { source_type?: string; page?: number; page_size?: number }) =>
    osintClient.get<T.OSINTResponse>(`/cases/${caseId}/osint/records`, { params }).then(res => res.data),

  // Domain Lookup
  domainLookup: (caseId: string, data: { domain: string }) =>
    osintClient.post<any>(`/cases/${caseId}/osint/domain-lookup`, data).then(res => res.data),

  // Social Intelligence
  expandSocial: (caseId: string, accountNodeId: string, data?: { depth?: number }) =>
    osintClient.post<any>(`/cases/${caseId}/osint/social-graph/${accountNodeId}/expand`, data).then(res => res.data),
  getSocialCommunities: (caseId: string, accountNodeId: string) =>
    osintClient.get<any>(`/cases/${caseId}/osint/social-graph/${accountNodeId}/communities`).then(res => res.data),

  // Crypto Tracking
  traceCrypto: (caseId: string, walletFacetId: string, data?: { max_depth?: number }) =>
    osintClient.post<any>(`/cases/${caseId}/osint/crypto/${walletFacetId}/trace`, data).then(res => res.data),
  getCryptoCluster: (caseId: string, walletFacetId: string) =>
    osintClient.get<any>(`/cases/${caseId}/osint/crypto/${walletFacetId}/cluster`).then(res => res.data),
  getCryptoFlow: (caseId: string, walletFacetId: string) =>
    osintClient.get<any>(`/cases/${caseId}/osint/crypto/${walletFacetId}/flow`).then(res => res.data),

  // Attribution Engine
  getAttributionProfile: (caseId: string, personId: string) =>
    osintClient.get<any>(`/cases/${caseId}/graph/person/${personId}/attribution-profile`).then(res => res.data),
  getAttributionCandidates: (caseId: string, personId: string, data?: { min_confidence?: number }) =>
    osintClient.post<any>(`/cases/${caseId}/graph/person/${personId}/attribution-candidates`, data).then(res => res.data),
  confirmIdentifier: (caseId: string, suggestionId: string) =>
    osintClient.post<any>(`/cases/${caseId}/graph/suggested-identifier/${suggestionId}/confirm`).then(res => res.data),
  rejectIdentifier: (caseId: string, suggestionId: string) =>
    osintClient.post<any>(`/cases/${caseId}/graph/suggested-identifier/${suggestionId}/reject`).then(res => res.data),
};
