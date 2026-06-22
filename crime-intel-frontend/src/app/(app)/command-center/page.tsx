'use client';

import React, { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useCaseStore } from '@/lib/store/case.store';
import {
  agentsApi, predictiveApi, explainApi, learningApi,
  acquisitionApi, osintDeepApi, digitalTwinApi, aiModelsApi,
  streamingApi,
} from '@/lib/api/client';
import {
  Brain, Shield, Clock, Search, TrendingUp, Zap, Network,
  AlertTriangle, CheckCircle, XCircle, Eye, ChevronRight,
  Activity, Cpu, Radio, Target, Fingerprint, BarChart3,
  Layers, ArrowRight, Sparkles, ChevronDown, Radar,
} from 'lucide-react';

const statusColors: Record<string, string> = {
  completed: '#22c55e',
  error: '#ef4444',
  active: '#3b82f6',
  warning: '#f59e0b',
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
  passing: '#22c55e',
  failing: '#ef4444',
};

const urgencyGradients: Record<string, string> = {
  critical: 'linear-gradient(135deg, #dc2626, #991b1b)',
  high: 'linear-gradient(135deg, #f97316, #c2410c)',
  medium: 'linear-gradient(135deg, #eab308, #a16207)',
  low: 'linear-gradient(135deg, #22c55e, #15803d)',
  immediate: 'linear-gradient(135deg, #dc2626, #991b1b)',
  within_24h: 'linear-gradient(135deg, #f97316, #c2410c)',
  within_48h: 'linear-gradient(135deg, #eab308, #a16207)',
  scheduled: 'linear-gradient(135deg, #22c55e, #15803d)',
};

export default function CommandCenterPage() {
  const { activeCaseId } = useCaseStore();
  const [activeTab, setActiveTab] = useState<string>('agents');
  const [osintQuery, setOsintQuery] = useState('');
  const [aiText, setAiText] = useState('');
  const [aiMode, setAiMode] = useState<string>('ner');

  // ── Data Queries ───────────────────────────────────────────────────────
  const agentsQuery = useQuery({
    queryKey: ['agents-analysis', activeCaseId],
    queryFn: () => agentsApi.runAnalysis(activeCaseId!),
    enabled: !!activeCaseId && activeTab === 'agents',
    staleTime: 60000,
  });

  const evidenceExpiryQuery = useQuery({
    queryKey: ['evidence-expiry', activeCaseId],
    queryFn: () => predictiveApi.evidenceExpiration(activeCaseId!),
    enabled: !!activeCaseId && activeTab === 'predictive',
    staleTime: 60000,
  });

  const seizureQuery = useQuery({
    queryKey: ['seizure-priority', activeCaseId],
    queryFn: () => predictiveApi.seizurePriority(activeCaseId!),
    enabled: !!activeCaseId && activeTab === 'predictive',
    staleTime: 60000,
  });

  const witnessQuery = useQuery({
    queryKey: ['witness-priority', activeCaseId],
    queryFn: () => predictiveApi.witnessPriority(activeCaseId!),
    enabled: !!activeCaseId && activeTab === 'predictive',
    staleTime: 60000,
  });

  const learningQuery = useQuery({
    queryKey: ['learning-analytics'],
    queryFn: () => learningApi.getAnalytics(),
    enabled: activeTab === 'learning',
    staleTime: 30000,
  });

  const modelsQuery = useQuery({
    queryKey: ['ai-models'],
    queryFn: () => aiModelsApi.getModelRegistry(),
    enabled: activeTab === 'ai-lab',
    staleTime: 60000,
  });

  const devicesQuery = useQuery({
    queryKey: ['connected-devices'],
    queryFn: () => acquisitionApi.detectDevices(),
    enabled: activeTab === 'acquisition',
    staleTime: 10000,
  });

  const digitalTwinQuery = useQuery({
    queryKey: ['digital-twin'],
    queryFn: () => digitalTwinApi.findSharedEntities(),
    enabled: activeTab === 'digital-twin',
    staleTime: 60000,
  });

  const streamingQuery = useQuery({
    queryKey: ['streaming-status'],
    queryFn: () => streamingApi.getStatus(),
    enabled: activeTab === 'streaming',
    staleTime: 5000,
  });

  const osintMutation = useMutation({
    mutationFn: (q: string) => osintDeepApi.runDeepOsint(q),
  });

  const aiAnalyzeMutation = useMutation({
    mutationFn: (params: { text: string; mode: string }) => {
      switch (params.mode) {
        case 'ner': return aiModelsApi.extractEntities(params.text);
        case 'sentiment': return aiModelsApi.analyzeSentiment(params.text);
        case 'intent': return aiModelsApi.classifyIntent(params.text);
        case 'deception': return aiModelsApi.scoreDeception(params.text);
        case 'stylometry': return aiModelsApi.analyzeStylometry(params.text);
        default: return aiModelsApi.extractEntities(params.text);
      }
    },
  });

  // ── Tab definitions ────────────────────────────────────────────────────
  const tabs = [
    { id: 'agents', label: 'Multi-Agent', icon: Brain, color: '#8b5cf6' },
    { id: 'predictive', label: 'Predictive Intel', icon: TrendingUp, color: '#f97316' },
    { id: 'ai-lab', label: 'AI Lab', icon: Cpu, color: '#06b6d4' },
    { id: 'acquisition', label: 'Acquisition', icon: Radio, color: '#22c55e' },
    { id: 'osint', label: 'Deep OSINT', icon: Search, color: '#3b82f6' },
    { id: 'digital-twin', label: 'Digital Twin', icon: Network, color: '#ec4899' },
    { id: 'learning', label: 'Learning', icon: BarChart3, color: '#a855f7' },
    { id: 'streaming', label: 'Live Stream', icon: Activity, color: '#ef4444' },
  ];

  if (!activeCaseId && !['ai-lab', 'acquisition', 'learning', 'streaming'].includes(activeTab)) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'rgba(255,255,255,0.5)' }}>
        <div style={{ textAlign: 'center' }}>
          <Radar size={64} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
          <h2 style={{ fontSize: 20, fontWeight: 600, margin: '0 0 8px' }}>Intelligence Command Center</h2>
          <p style={{ fontSize: 14 }}>Select an active case to access predictive intelligence, multi-agent analysis, and more.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0a0a0f', color: '#e2e8f0' }}>
      {/* Header */}
      <div style={{
        padding: '20px 24px 0',
        background: 'linear-gradient(180deg, rgba(139,92,246,0.08) 0%, transparent 100%)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <div style={{
            width: 42, height: 42, borderRadius: 12,
            background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Radar size={22} color="white" />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em' }}>
              Intelligence Command Center
            </h1>
            <p style={{ margin: 0, fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>
              Multi-Agent Analysis • Predictive Intelligence • Decision Support
            </p>
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
            <span style={{
              padding: '4px 10px', borderRadius: 20, fontSize: 11,
              background: 'rgba(34,197,94,0.15)', color: '#22c55e', fontWeight: 600,
            }}>● LIVE</span>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 2, overflowX: 'auto', paddingBottom: 0 }}>
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '10px 16px', border: 'none', borderRadius: '8px 8px 0 0',
                background: activeTab === tab.id ? 'rgba(255,255,255,0.08)' : 'transparent',
                color: activeTab === tab.id ? tab.color : 'rgba(255,255,255,0.4)',
                cursor: 'pointer', fontSize: 13, fontWeight: 600,
                borderBottom: activeTab === tab.id ? `2px solid ${tab.color}` : '2px solid transparent',
                transition: 'all 0.2s ease',
                whiteSpace: 'nowrap',
              }}
            >
              <tab.icon size={15} />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>

        {/* ── Multi-Agent Analysis ────────────────────────────────────────── */}
        {activeTab === 'agents' && (
          <div>
            {agentsQuery.isLoading && <LoadingPulse label="Running 7 specialized agents..." />}
            {agentsQuery.error && <ErrorCard error="Agent analysis failed. Is the backend running?" />}
            {agentsQuery.data && (
              <>
                {/* Agent Status Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
                  {Object.entries(agentsQuery.data.agent_statuses || {}).map(([name, status]: [string, any]) => (
                    <div key={name} style={{
                      padding: 14, borderRadius: 12,
                      background: 'rgba(255,255,255,0.03)',
                      border: `1px solid ${status.status === 'completed' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                        {status.status === 'completed' ?
                          <CheckCircle size={14} color="#22c55e" /> :
                          <XCircle size={14} color="#ef4444" />
                        }
                        <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          {name.replace('_', ' ')}
                        </span>
                      </div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: statusColors[status.status] || '#94a3b8' }}>
                        {status.recommendations || 0}
                      </div>
                      <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)' }}>recommendations</div>
                    </div>
                  ))}
                </div>

                {/* Consensus Summary */}
                <div style={{
                  padding: 16, borderRadius: 12, marginBottom: 20,
                  background: 'linear-gradient(135deg, rgba(139,92,246,0.1), rgba(99,102,241,0.05))',
                  border: '1px solid rgba(139,92,246,0.2)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <Sparkles size={16} color="#8b5cf6" />
                    <span style={{ fontSize: 13, fontWeight: 700, color: '#8b5cf6' }}>Agent Consensus</span>
                  </div>
                  <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'rgba(255,255,255,0.8)' }}>
                    {agentsQuery.data.consensus_summary}
                  </p>
                </div>

                {/* Priority Actions & Alerts */}
                {agentsQuery.data.directive?.priority_actions?.length > 0 && (
                  <div style={{ marginBottom: 20 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: '#f97316' }}>⚡ Priority Actions</h3>
                    {agentsQuery.data.directive.priority_actions.map((rec: any, i: number) => (
                      <RecommendationCard key={i} rec={rec} />
                    ))}
                  </div>
                )}
                {agentsQuery.data.directive?.critical_alerts?.length > 0 && (
                  <div>
                    <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: '#ef4444' }}>🚨 Critical Alerts</h3>
                    {agentsQuery.data.directive.critical_alerts.map((rec: any, i: number) => (
                      <RecommendationCard key={i} rec={rec} />
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── Predictive Intelligence ──────────────────────────────────────── */}
        {activeTab === 'predictive' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            {/* Evidence Expiration */}
            <div style={{
              gridColumn: '1 / -1', padding: 20, borderRadius: 14,
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
            }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Clock size={18} color="#f97316" /> Evidence at Risk of Expiring
              </h3>
              {evidenceExpiryQuery.isLoading && <LoadingPulse label="Analyzing evidence lifecycles..." />}
              {evidenceExpiryQuery.data?.at_risk_evidence?.map((item: any, i: number) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
                  borderRadius: 8, marginBottom: 6,
                  background: item.urgency === 'critical' ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${item.urgency === 'critical' ? 'rgba(239,68,68,0.2)' : 'rgba(255,255,255,0.04)'}`,
                }}>
                  <div style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: urgencyGradients[item.urgency] || '#94a3b8',
                    flexShrink: 0,
                  }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{item.evidence_type.replace(/_/g, ' ')}</div>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.recommended_action}
                    </div>
                  </div>
                  <div style={{
                    padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
                    background: urgencyGradients[item.urgency],
                    color: 'white',
                  }}>
                    {item.days_remaining === 0 ? 'NOW' : `${item.days_remaining}d`}
                  </div>
                </div>
              ))}
              {evidenceExpiryQuery.data?.at_risk_count === 0 && (
                <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 13 }}>No evidence at risk of expiring.</p>
              )}
            </div>

            {/* Seizure Priority */}
            <div style={{
              padding: 20, borderRadius: 14,
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
            }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Target size={18} color="#ef4444" /> Seizure Priority
              </h3>
              {seizureQuery.isLoading && <LoadingPulse label="Computing..." />}
              {seizureQuery.data?.seizure_targets?.slice(0, 5).map((t: any, i: number) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '8px 12px', borderRadius: 8, marginBottom: 4,
                  background: 'rgba(255,255,255,0.02)',
                }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{t.name}</div>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{t.type} • {t.device_type || ''}</div>
                  </div>
                  <div style={{
                    padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
                    background: urgencyGradients[t.urgency], color: 'white',
                  }}>{t.urgency}</div>
                </div>
              ))}
            </div>

            {/* Witness Priority */}
            <div style={{
              padding: 20, borderRadius: 14,
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
            }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Eye size={18} color="#3b82f6" /> Witness Priority
              </h3>
              {witnessQuery.isLoading && <LoadingPulse label="Ranking witnesses..." />}
              {witnessQuery.data?.witnesses_ranked?.slice(0, 5).map((w: any, i: number) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '8px 12px', borderRadius: 8, marginBottom: 4,
                  background: 'rgba(255,255,255,0.02)',
                }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{w.name || w.witness_id?.slice(0, 8)}</div>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{w.role} • {w.event_involvement} events</div>
                  </div>
                  <div style={{
                    padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
                    background: urgencyGradients[w.recommended_timing], color: 'white',
                  }}>{w.recommended_timing}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── AI Lab ───────────────────────────────────────────────────────── */}
        {activeTab === 'ai-lab' && (
          <div>
            {/* Model Registry */}
            <div style={{ marginBottom: 24 }}>
              <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Cpu size={18} color="#06b6d4" /> AI Model Registry
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
                {modelsQuery.data?.models?.map((m: any, i: number) => (
                  <div key={i} style={{
                    padding: 14, borderRadius: 12,
                    background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(6,182,212,0.15)',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ fontSize: 13, fontWeight: 700 }}>{m.name}</span>
                      <span style={{
                        padding: '2px 8px', borderRadius: 12, fontSize: 10, fontWeight: 600,
                        background: m.status === 'active' ? 'rgba(34,197,94,0.15)' : 'rgba(245,158,11,0.15)',
                        color: m.status === 'active' ? '#22c55e' : '#f59e0b',
                      }}>{m.status}</span>
                    </div>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>
                      {m.version} • {m.backend}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Live Analysis */}
            <div style={{
              padding: 20, borderRadius: 14,
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
            }}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700 }}>🧪 Live Analysis Sandbox</h3>
              <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                {['ner', 'sentiment', 'intent', 'deception', 'stylometry'].map(mode => (
                  <button key={mode} onClick={() => setAiMode(mode)} style={{
                    padding: '6px 14px', borderRadius: 20, border: 'none',
                    background: aiMode === mode ? 'rgba(6,182,212,0.2)' : 'rgba(255,255,255,0.05)',
                    color: aiMode === mode ? '#06b6d4' : 'rgba(255,255,255,0.5)',
                    cursor: 'pointer', fontSize: 12, fontWeight: 600,
                  }}>
                    {mode.toUpperCase()}
                  </button>
                ))}
              </div>
              <textarea
                value={aiText}
                onChange={e => setAiText(e.target.value)}
                placeholder="Paste text to analyze..."
                style={{
                  width: '100%', minHeight: 80, padding: 12, borderRadius: 8,
                  background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)',
                  color: '#e2e8f0', fontSize: 13, resize: 'vertical', fontFamily: 'inherit',
                }}
              />
              <button
                onClick={() => aiAnalyzeMutation.mutate({ text: aiText, mode: aiMode })}
                disabled={!aiText.trim() || aiAnalyzeMutation.isPending}
                style={{
                  margin: '12px 0', padding: '8px 20px', borderRadius: 8, border: 'none',
                  background: 'linear-gradient(135deg, #06b6d4, #0891b2)',
                  color: 'white', fontWeight: 700, cursor: 'pointer', fontSize: 13,
                  opacity: !aiText.trim() ? 0.5 : 1,
                }}
              >
                {aiAnalyzeMutation.isPending ? 'Analyzing...' : `Run ${aiMode.toUpperCase()}`}
              </button>
              {aiAnalyzeMutation.data && (
                <pre style={{
                  padding: 14, borderRadius: 8, background: 'rgba(0,0,0,0.4)',
                  fontSize: 12, overflow: 'auto', maxHeight: 300,
                  border: '1px solid rgba(6,182,212,0.2)', color: '#94a3b8',
                }}>
                  {JSON.stringify(aiAnalyzeMutation.data, null, 2)}
                </pre>
              )}
            </div>
          </div>
        )}

        {/* ── Acquisition ──────────────────────────────────────────────────── */}
        {activeTab === 'acquisition' && (
          <div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Radio size={18} color="#22c55e" /> Connected Devices
            </h3>
            {devicesQuery.isLoading && <LoadingPulse label="Scanning USB ports..." />}
            {devicesQuery.data?.devices?.length === 0 && (
              <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 13 }}>No external devices detected.</p>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
              {devicesQuery.data?.devices?.map((dev: any, i: number) => (
                <div key={i} style={{
                  padding: 16, borderRadius: 12,
                  background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(34,197,94,0.15)',
                }}>
                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{dev.model}</div>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>
                    {dev.device_type} • {dev.interface} {dev.size_gb ? `• ${dev.size_gb} GB` : ''}
                  </div>
                  {dev.serial && <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.25)', marginTop: 4, fontFamily: 'monospace' }}>S/N: {dev.serial}</div>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Deep OSINT ────────────────────────────────────────────────────── */}
        {activeTab === 'osint' && (
          <div>
            <div style={{
              padding: 20, borderRadius: 14, marginBottom: 20,
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(59,130,246,0.15)',
            }}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Search size={18} color="#3b82f6" /> Deep OSINT Search
              </h3>
              <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', margin: '0 0 12px' }}>
                Search across DNS, certificate transparency, dark web indicators, blockchain, threat intel, and leak databases.
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  value={osintQuery}
                  onChange={e => setOsintQuery(e.target.value)}
                  placeholder="Enter IP, domain, email, or wallet address..."
                  onKeyDown={e => e.key === 'Enter' && osintQuery && osintMutation.mutate(osintQuery)}
                  style={{
                    flex: 1, padding: '10px 14px', borderRadius: 8,
                    background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#e2e8f0', fontSize: 13,
                  }}
                />
                <button
                  onClick={() => osintQuery && osintMutation.mutate(osintQuery)}
                  disabled={!osintQuery || osintMutation.isPending}
                  style={{
                    padding: '10px 20px', borderRadius: 8, border: 'none',
                    background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
                    color: 'white', fontWeight: 700, cursor: 'pointer', fontSize: 13,
                  }}
                >
                  {osintMutation.isPending ? '⏳' : '🔍 Search'}
                </button>
              </div>
            </div>
            {osintMutation.data && (
              <pre style={{
                padding: 16, borderRadius: 12, background: 'rgba(0,0,0,0.3)',
                fontSize: 12, overflow: 'auto', maxHeight: 500,
                border: '1px solid rgba(59,130,246,0.15)', color: '#94a3b8',
              }}>
                {JSON.stringify(osintMutation.data, null, 2)}
              </pre>
            )}
          </div>
        )}

        {/* ── Digital Twin ──────────────────────────────────────────────────── */}
        {activeTab === 'digital-twin' && (
          <div>
            <div style={{
              padding: 20, borderRadius: 14, marginBottom: 20,
              background: 'linear-gradient(135deg, rgba(236,72,153,0.08), rgba(168,85,247,0.04))',
              border: '1px solid rgba(236,72,153,0.2)',
            }}>
              <h3 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Network size={18} color="#ec4899" /> Cross-Case Entity Links
              </h3>
              <p style={{ margin: 0, fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>
                Entities appearing across multiple investigations — same wallet, phone, IMEI, email, or person.
              </p>
            </div>
            {digitalTwinQuery.isLoading && <LoadingPulse label="Scanning cross-case entity graph..." />}
            {digitalTwinQuery.data?.shared_entities?.map((e: any, i: number) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 14px', borderRadius: 8, marginBottom: 6,
                background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(236,72,153,0.1)',
              }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{e.value}</div>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{e.entity_type}</div>
                </div>
                <div style={{
                  padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 700,
                  background: 'rgba(236,72,153,0.15)', color: '#ec4899',
                }}>
                  {e.case_count} cases
                </div>
              </div>
            ))}
            {digitalTwinQuery.data?.total_found === 0 && (
              <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 13, textAlign: 'center', padding: 40 }}>
                No cross-case entity links found yet. Entities will appear here as multiple investigations share common identifiers.
              </p>
            )}
          </div>
        )}

        {/* ── Learning System ──────────────────────────────────────────────── */}
        {activeTab === 'learning' && (
          <div>
            {learningQuery.isLoading && <LoadingPulse label="Loading learning analytics..." />}
            {learningQuery.data && (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
                  <StatCard label="Feedback Entries" value={learningQuery.data.total_feedback_entries} color="#a855f7" />
                  <StatCard label="Cases Tracked" value={learningQuery.data.total_cases_tracked} color="#3b82f6" />
                  <StatCard label="Overall Accuracy" value={`${(learningQuery.data.overall_accuracy * 100).toFixed(1)}%`} color="#22c55e" />
                  <StatCard label="Learning Rate" value={learningQuery.data.learning_rate} color="#f97316" />
                </div>

                <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Model Weights</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8 }}>
                  {Object.entries(learningQuery.data.current_weights || {}).map(([name, weight]: [string, any]) => (
                    <div key={name} style={{
                      padding: 12, borderRadius: 8,
                      background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)',
                    }}>
                      <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 4 }}>{name}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{
                          flex: 1, height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.05)',
                          overflow: 'hidden',
                        }}>
                          <div style={{
                            width: `${Math.min((weight as number) / 2 * 100, 100)}%`,
                            height: '100%', borderRadius: 3,
                            background: (weight as number) > 1.0 ? '#22c55e' : (weight as number) < 0.5 ? '#ef4444' : '#3b82f6',
                          }} />
                        </div>
                        <span style={{ fontSize: 12, fontWeight: 700, minWidth: 36 }}>{(weight as number).toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* ── Live Streaming ───────────────────────────────────────────────── */}
        {activeTab === 'streaming' && (
          <div>
            {streamingQuery.isLoading && <LoadingPulse label="Checking streaming status..." />}
            {streamingQuery.data && (
              <>
                <div style={{
                  padding: 20, borderRadius: 14, marginBottom: 20,
                  background: 'linear-gradient(135deg, rgba(239,68,68,0.08), rgba(220,38,38,0.04))',
                  border: '1px solid rgba(239,68,68,0.2)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <Activity size={18} color="#ef4444" />
                    <span style={{ fontSize: 16, fontWeight: 700 }}>Real-Time Pipeline</span>
                    <span style={{
                      marginLeft: 'auto', padding: '4px 10px', borderRadius: 20,
                      background: 'rgba(34,197,94,0.15)', color: '#22c55e',
                      fontSize: 11, fontWeight: 600,
                    }}>
                      {streamingQuery.data.pipeline.status.toUpperCase()}
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 22, fontWeight: 700, color: '#22c55e' }}>
                        {streamingQuery.data.pipeline.evidence_to_graph_latency_ms}ms
                      </div>
                      <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>Evidence → Graph</div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 22, fontWeight: 700, color: '#3b82f6' }}>
                        {streamingQuery.data.pipeline.graph_to_theory_latency_ms}ms
                      </div>
                      <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>Graph → Theory</div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 22, fontWeight: 700, color: '#f97316' }}>
                        {streamingQuery.data.pipeline.theory_to_legal_latency_ms}ms
                      </div>
                      <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>Theory → Legal</div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 22, fontWeight: 700, color: '#8b5cf6' }}>
                        {streamingQuery.data.pipeline.total_pipeline_latency_ms}ms
                      </div>
                      <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>Total Pipeline</div>
                    </div>
                  </div>
                </div>

                <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Kafka Topics</h3>
                {streamingQuery.data.kafka.topics.map((topic: any, i: number) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '10px 14px', borderRadius: 8, marginBottom: 6,
                    background: 'rgba(255,255,255,0.03)',
                  }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#22c55e', flexShrink: 0 }} />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'monospace' }}>{topic.name}</div>
                      <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>{topic.description}</div>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────

function LoadingPulse({ label }: { label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 20, justifyContent: 'center' }}>
      <div style={{
        width: 12, height: 12, borderRadius: '50%', background: '#8b5cf6',
        animation: 'pulse 1.5s ease-in-out infinite',
      }} />
      <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)' }}>{label}</span>
      <style>{`@keyframes pulse { 0%,100% { opacity: 0.3; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.2); } }`}</style>
    </div>
  );
}

function ErrorCard({ error }: { error: string }) {
  return (
    <div style={{
      padding: 16, borderRadius: 12, background: 'rgba(239,68,68,0.08)',
      border: '1px solid rgba(239,68,68,0.2)', color: '#fca5a5', fontSize: 13,
    }}>
      <AlertTriangle size={16} style={{ marginRight: 8, verticalAlign: 'middle' }} />
      {error}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: any; color: string }) {
  return (
    <div style={{
      padding: 16, borderRadius: 12,
      background: `linear-gradient(135deg, ${color}10, ${color}05)`,
      border: `1px solid ${color}30`,
    }}>
      <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}

function RecommendationCard({ rec }: { rec: any }) {
  return (
    <div style={{
      padding: 14, borderRadius: 10, marginBottom: 8,
      background: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.06)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{
          padding: '2px 8px', borderRadius: 12, fontSize: 10, fontWeight: 600,
          background: 'rgba(139,92,246,0.15)', color: '#8b5cf6',
        }}>{rec.agent_role}</span>
        <span style={{ fontSize: 13, fontWeight: 700 }}>{rec.title}</span>
        <span style={{
          marginLeft: 'auto', fontSize: 11, fontWeight: 700,
          color: rec.confidence > 0.8 ? '#22c55e' : rec.confidence > 0.5 ? '#eab308' : '#ef4444',
        }}>
          {(rec.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <p style={{ margin: '0 0 6px', fontSize: 12, color: 'rgba(255,255,255,0.6)', lineHeight: 1.5 }}>{rec.description}</p>
      {rec.suggested_action && (
        <div style={{ fontSize: 11, color: '#3b82f6', display: 'flex', alignItems: 'center', gap: 4 }}>
          <ArrowRight size={12} /> {rec.suggested_action}
        </div>
      )}
    </div>
  );
}
