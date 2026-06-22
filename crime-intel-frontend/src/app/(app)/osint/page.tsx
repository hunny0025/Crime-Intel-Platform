'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { osintApi } from '@/lib/api/osint-client';
import { useCaseStore } from '@/lib/store/case.store';
import { 
  PageHeader, IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, IntelCardFooter,
  EmptyState, IntelBadge 
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { 
  Globe, Search, RefreshCw, Send, Radio, UserCheck, 
  Wallet, Network, ArrowRight, CheckCircle2, ShieldAlert, Loader2 
} from 'lucide-react';

export default function OsintPage() {
  const queryClient = useQueryClient();
  const { activeCaseId } = useCaseStore();
  const [activeTab, setActiveTab] = useState<'records' | 'domain' | 'crypto' | 'social'>('records');

  // Input states
  const [domainInput, setDomainInput] = useState('');
  const [cryptoInput, setCryptoInput] = useState('');
  const [socialInput, setSocialInput] = useState('');

  // Query: Fetch OSINT records
  const { data: osintData, isLoading, refetch } = useQuery({
    queryKey: ['osint-records', activeCaseId],
    queryFn: () => osintApi.listRecords(activeCaseId!),
    enabled: !!activeCaseId,
  });

  const records = osintData?.records || [];

  // Mutations
  const domainLookupMutation = useMutation({
    mutationFn: (domain: string) => osintApi.domainLookup(activeCaseId!, { domain }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['osint-records', activeCaseId] });
      setDomainInput('');
      setActiveTab('records');
    }
  });

  const cryptoTraceMutation = useMutation({
    mutationFn: (wallet: string) => osintApi.traceCrypto(activeCaseId!, wallet),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['osint-records', activeCaseId] });
      setCryptoInput('');
      setActiveTab('records');
    }
  });

  const socialExpandMutation = useMutation({
    mutationFn: (accountNodeId: string) => osintApi.expandSocial(activeCaseId!, accountNodeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['osint-records', activeCaseId] });
      setSocialInput('');
      setActiveTab('records');
    }
  });

  const handleDomainLookup = (e: React.FormEvent) => {
    e.preventDefault();
    domainLookupMutation.mutate(domainInput);
  };

  const handleCryptoTrace = (e: React.FormEvent) => {
    e.preventDefault();
    cryptoTraceMutation.mutate(cryptoInput);
  };

  const handleSocialExpand = (e: React.FormEvent) => {
    e.preventDefault();
    socialExpandMutation.mutate(socialInput);
  };

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the OSINT workspace."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader 
        title="OSINT Intelligence Hub" 
        description="Trigger DNS queries, scrape social nodes, trace cryptocurrency transactions, and verify public profiles."
      />

      {/* Main Hub Tabs */}
      <div className="flex gap-2 bg-surface/50 p-1 rounded-xl border border-border-subtle/50 w-fit">
        <button
          onClick={() => setActiveTab('records')}
          className={cn(
            "px-4 py-2 rounded-lg text-xs font-mono font-bold uppercase transition-all flex items-center gap-2",
            activeTab === 'records' ? "bg-intel-blue text-obsidian" : "text-text-secondary hover:text-text-primary"
          )}
        >
          <Radio className="w-3.5 h-3.5" />
          <span>Scraped Logs ({records.length})</span>
        </button>
        <button
          onClick={() => setActiveTab('domain')}
          className={cn(
            "px-4 py-2 rounded-lg text-xs font-mono font-bold uppercase transition-all flex items-center gap-2",
            activeTab === 'domain' ? "bg-intel-blue text-obsidian" : "text-text-secondary hover:text-text-primary"
          )}
        >
          <Globe className="w-3.5 h-3.5" />
          <span>Domain DNS lookup</span>
        </button>
        <button
          onClick={() => setActiveTab('crypto')}
          className={cn(
            "px-4 py-2 rounded-lg text-xs font-mono font-bold uppercase transition-all flex items-center gap-2",
            activeTab === 'crypto' ? "bg-intel-blue text-obsidian" : "text-text-secondary hover:text-text-primary"
          )}
        >
          <Wallet className="w-3.5 h-3.5" />
          <span>Crypto Trace</span>
        </button>
        <button
          onClick={() => setActiveTab('social')}
          className={cn(
            "px-4 py-2 rounded-lg text-xs font-mono font-bold uppercase transition-all flex items-center gap-2",
            activeTab === 'social' ? "bg-intel-blue text-obsidian" : "text-text-secondary hover:text-text-primary"
          )}
        >
          <Network className="w-3.5 h-3.5" />
          <span>Social Scraping</span>
        </button>
      </div>

      <div className="min-h-[400px]">
        {/* 1. RECORDS TAB */}
        {activeTab === 'records' && (
          <div className="space-y-4">
            {isLoading ? (
              <div className="space-y-4">
                {[1, 2].map((_, i) => (
                  <div key={i} className="h-20 bg-surface rounded animate-pulse" />
                ))}
              </div>
            ) : records.length === 0 ? (
              <EmptyState 
                title="OSINT ledger is empty" 
                description="No public records scraped for this case. Use the DNS, social, or crypto tools to query public assets."
                icon={Search}
              />
            ) : (
              <div className="space-y-3">
                {records.map((rec) => (
                  <IntelCard key={rec.record_id}>
                    <IntelCardHeader className="py-4">
                      <div className="flex justify-between items-start gap-4">
                        <div className="flex items-center gap-2.5">
                          <Globe className="w-4 h-4 text-intel-cyan" />
                          <span className="text-xs font-mono font-bold text-text-primary uppercase">
                            Source: {rec.source_type}
                          </span>
                        </div>
                        <span className="text-[10px] font-mono text-text-muted">
                          {new Date(rec.retrieved_at).toLocaleString()}
                        </span>
                      </div>
                    </IntelCardHeader>
                    <IntelCardContent className="py-2 space-y-3">
                      <div className="bg-base/50 p-3 rounded border border-border-subtle font-mono text-xs text-text-secondary select-all">
                        Query Parameter: {rec.query}
                      </div>
                      <div className="space-y-1">
                        <span className="text-[9px] font-mono font-bold text-text-secondary uppercase">Raw result payload</span>
                        <pre className="bg-base/20 border border-border-subtle/50 p-3 rounded-lg font-mono text-[10px] text-intel-cyan overflow-x-auto max-h-40">
                          {JSON.stringify(rec.raw_result, null, 2)}
                        </pre>
                      </div>
                    </IntelCardContent>
                  </IntelCard>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 2. DOMAIN DNS TAB */}
        {activeTab === 'domain' && (
          <IntelCard className="max-w-xl mx-auto">
            <IntelCardHeader>
              <IntelCardTitle>
                <Globe className="w-5 h-5 text-intel-blue" />
                <span>DNS / WHOIS Lookup</span>
              </IntelCardTitle>
            </IntelCardHeader>
            <form onSubmit={handleDomainLookup}>
              <IntelCardContent className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-secondary">
                    Target Domain Name
                  </label>
                  <input
                    type="text"
                    value={domainInput}
                    onChange={(e) => setDomainInput(e.target.value)}
                    className="w-full bg-base border border-border rounded-lg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-intel-blue/60"
                    placeholder="e.g. suspect-domain.com"
                    required
                  />
                </div>
              </IntelCardContent>
              <IntelCardFooter>
                <Button 
                  type="submit" 
                  className="w-full bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-xs"
                  disabled={domainLookupMutation.isPending}
                >
                  {domainLookupMutation.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : "EXECUTE DNS SCRAPE"}
                </Button>
              </IntelCardFooter>
            </form>
          </IntelCard>
        )}

        {/* 3. CRYPTO TAB */}
        {activeTab === 'crypto' && (
          <IntelCard className="max-w-xl mx-auto">
            <IntelCardHeader>
              <IntelCardTitle>
                <Wallet className="w-5 h-5 text-intel-blue" />
                <span>Transaction Tracing</span>
              </IntelCardTitle>
            </IntelCardHeader>
            <form onSubmit={handleCryptoTrace}>
              <IntelCardContent className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-secondary">
                    Wallet Identifier / Key ID
                  </label>
                  <input
                    type="text"
                    value={cryptoInput}
                    onChange={(e) => setCryptoInput(e.target.value)}
                    className="w-full bg-base border border-border rounded-lg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-intel-blue/60"
                    placeholder="e.g. 0x71C7656EC7ab88b098defB751B7401B5f6d8976F"
                    required
                  />
                </div>
              </IntelCardContent>
              <IntelCardFooter>
                <Button 
                  type="submit" 
                  className="w-full bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-xs"
                  disabled={cryptoTraceMutation.isPending}
                >
                  {cryptoTraceMutation.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : "TRACE BLOCKCHAIN FLOWS"}
                </Button>
              </IntelCardFooter>
            </form>
          </IntelCard>
        )}

        {/* 4. SOCIAL TAB */}
        {activeTab === 'social' && (
          <IntelCard className="max-w-xl mx-auto">
            <IntelCardHeader>
              <IntelCardTitle>
                <Network className="w-5 h-5 text-intel-blue" />
                <span>Expand Social Graph</span>
              </IntelCardTitle>
            </IntelCardHeader>
            <form onSubmit={handleSocialExpand}>
              <IntelCardContent className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-secondary">
                    Target Node UUID (Account Node)
                  </label>
                  <input
                    type="text"
                    value={socialInput}
                    onChange={(e) => setSocialInput(e.target.value)}
                    className="w-full bg-base border border-border rounded-lg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-intel-blue/60"
                    placeholder="Enter account node uuid..."
                    required
                  />
                </div>
              </IntelCardContent>
              <IntelCardFooter>
                <Button 
                  type="submit" 
                  className="w-full bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-xs"
                  disabled={socialExpandMutation.isPending}
                >
                  {socialExpandMutation.isPending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : "TRIGGER SCRAPING SCAN"}
                </Button>
              </IntelCardFooter>
            </form>
          </IntelCard>
        )}
      </div>
    </div>
  );
}

// Quick helper
function cn(...classes: any[]) {
  return classes.filter(Boolean).join(' ');
}
