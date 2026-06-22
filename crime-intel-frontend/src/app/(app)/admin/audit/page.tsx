'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { ingestionApi } from '@/lib/api/client';
import { useCaseStore } from '@/lib/store/case.store';
import { 
  PageHeader, IntelCard, IntelCardHeader, IntelCardTitle, IntelCardContent, 
  EmptyState, Table, TableHeader, TableBody, TableRow, TableCell, TableHead 
} from '@/components/ui';
import { Button } from '@/components/ui/button';
import { History, RefreshCw } from 'lucide-react';

export default function AuditPage() {
  const { activeCaseId } = useCaseStore();

  const { data: logs = [], isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['ingestion-audit', activeCaseId],
    queryFn: () => ingestionApi.getAuditLog(activeCaseId!),
    enabled: !!activeCaseId,
  });

  if (!activeCaseId) {
    return (
      <EmptyState 
        title="No active case workspace" 
        description="Please select an active case from the top header or cases explorer to view the ingestion audit logs."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader 
        title="Ingestion Audit Logs" 
        description="Verifiable timeline of ingestion operations, Kafka transaction tracking, and source file metadata logs."
        actions={
          <Button 
            variant="secondary"
            onClick={() => refetch()}
            disabled={isLoading || isRefetching}
            className="font-mono text-xs border-border-subtle"
          >
            <RefreshCw className={isRefetching ? "w-3.5 h-3.5 animate-spin" : "w-3.5 h-3.5"} />
          </Button>
        }
      />

      <IntelCard>
        <IntelCardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Audit Reference ID</TableHead>
                <TableHead>Uploader Agent</TableHead>
                <TableHead>Source Format</TableHead>
                <TableHead>Artifacts Created</TableHead>
                <TableHead>Ingestion Timestamp</TableHead>
                <TableHead>Kafka Event ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-6 text-text-muted font-mono">
                    Loading ingestion registers...
                  </TableCell>
                </TableRow>
              ) : logs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-10 text-text-muted font-mono">
                    No ingestion logs cataloged under this case file ledger.
                  </TableCell>
                </TableRow>
              ) : (
                logs.map((log) => (
                  <TableRow key={log.audit_id}>
                    <TableCell className="font-mono text-xs font-bold text-intel-blue select-all">
                      {log.audit_id.slice(0, 8)}...
                    </TableCell>
                    <TableCell className="font-sans font-semibold text-text-primary">{log.actor}</TableCell>
                    <TableCell className="font-mono text-xs text-text-secondary uppercase">{log.source_format}</TableCell>
                    <TableCell className="font-mono text-xs font-bold text-intel-green">{log.num_artifacts}</TableCell>
                    <TableCell className="font-mono text-xs text-text-secondary">
                      {new Date(log.timestamp).toLocaleString()}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-text-muted select-all">
                      {log.kafka_event_id.slice(0, 8)}...
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </IntelCardContent>
      </IntelCard>
    </div>
  );
}
