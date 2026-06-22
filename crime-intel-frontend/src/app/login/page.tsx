'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/store/auth.store';
import { IntelCard, IntelCardHeader, IntelCardTitle, IntelCardDescription, IntelCardContent, IntelCardFooter } from '@/components/ui/intel-card';
import { Button } from '@/components/ui/button';
import { ShieldCheck, User, Building, ShieldAlert } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const { login, isAuthenticated } = useAuthStore();

  const [username, setUsername] = useState('investigator_alpha');
  const [agency, setAgency] = useState('CBI');
  const [role, setRole] = useState('Lead Investigator');

  useEffect(() => {
    if (isAuthenticated) {
      router.push('/');
    }
  }, [isAuthenticated, router]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    login(username, agency, role);
    router.push('/');
  };

  return (
    <div className="min-h-screen bg-obsidian flex items-center justify-center p-4 relative overflow-hidden">
      {/* Decorative ambient glows */}
      <div className="absolute top-[20%] left-[20%] w-[350px] h-[350px] rounded-full bg-intel-blue/5 blur-[100px] pointer-events-none" />
      <div className="absolute bottom-[20%] right-[20%] w-[350px] h-[350px] rounded-full bg-intel-purple/5 blur-[100px] pointer-events-none" />

      <div className="w-full max-w-md z-10">
        <div className="flex flex-col items-center mb-8">
          <div className="h-12 w-12 rounded-xl bg-intel-blue flex items-center justify-center font-bold text-obsidian text-lg mb-3 shadow-[0_0_20px_rgba(74,158,255,0.4)]">
            IOS
          </div>
          <h1 className="text-xl font-bold font-mono tracking-widest text-text-primary">
            INVESTIGATION OS
          </h1>
          <p className="text-xs text-text-secondary uppercase tracking-widest mt-1">
            National Crime Intelligence Platform
          </p>
        </div>

        <IntelCard glowColor="blue" glass>
          <IntelCardHeader>
            <IntelCardTitle>
              <ShieldCheck className="w-5 h-5 text-intel-blue" />
              <span>Identity Verification</span>
            </IntelCardTitle>
            <IntelCardDescription>
              Access restricted to cleared law enforcement and intelligence personnel.
            </IntelCardDescription>
          </IntelCardHeader>

          <form onSubmit={handleSubmit}>
            <IntelCardContent className="space-y-4">
              {/* Username */}
              <div className="space-y-1.5">
                <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-secondary flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5" />
                  <span>Investigator Credential</span>
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-base border border-border rounded-lg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-intel-blue/60 transition-colors"
                  required
                />
              </div>

              {/* Agency */}
              <div className="space-y-1.5">
                <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-secondary flex items-center gap-1.5">
                  <Building className="w-3.5 h-3.5" />
                  <span>Assigned Agency</span>
                </label>
                <select
                  value={agency}
                  onChange={(e) => setAgency(e.target.value)}
                  className="w-full bg-base border border-border rounded-lg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-intel-blue/60 transition-colors"
                >
                  <option value="CBI">Central Bureau of Investigation (CBI)</option>
                  <option value="NIA">National Investigation Agency (NIA)</option>
                  <option value="IB">Intelligence Bureau (IB)</option>
                  <option value="RAW">Research and Analysis Wing (R&AW)</option>
                </select>
              </div>

              {/* Role */}
              <div className="space-y-1.5">
                <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-text-secondary flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5" />
                  <span>Tactical Operations Role</span>
                </label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full bg-base border border-border rounded-lg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:border-intel-blue/60 transition-colors"
                >
                  <option value="Lead Investigator">Lead Investigator</option>
                  <option value="Field Operative">Field Operative</option>
                  <option value="Forensic Analyst">Forensic Analyst</option>
                  <option value="System Administrator">System Administrator</option>
                </select>
              </div>
            </IntelCardContent>

            <IntelCardFooter className="flex flex-col gap-3">
              <Button type="submit" className="w-full bg-intel-blue hover:bg-intel-blue/80 text-obsidian font-mono font-bold text-xs py-2.5 rounded-lg shadow-[0_0_15px_rgba(74,158,255,0.2)]">
                AUTHENTICATE AND DEPLOY
              </Button>
              <div className="text-[10px] font-mono text-text-muted text-center leading-normal">
                SYSTEM AUDITING ACTIVE. ALL LOGINS ARE RECORDED UNDER IND-RESTRICTED-CBR-2026.
              </div>
            </IntelCardFooter>
          </form>
        </IntelCard>
      </div>
    </div>
  );
}
