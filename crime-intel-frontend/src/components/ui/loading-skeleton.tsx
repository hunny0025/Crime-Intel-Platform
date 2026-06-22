import * as React from "react"
import { cn } from "@/lib/utils"

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {}

function Skeleton({ className, ...props }: SkeletonProps) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-elevated border border-border-subtle/40", className)}
      {...props}
    />
  )
}

function StatCardSkeleton() {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface p-6 space-y-4">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  )
}

function TableSkeleton({ rows = 5, cols = 4 }) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface overflow-hidden">
      <div className="p-4 border-b border-border-subtle/50 flex justify-between items-center">
        <Skeleton className="h-6 w-1/4" />
        <Skeleton className="h-8 w-1/6" />
      </div>
      <div className="p-4 space-y-4">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex gap-4 items-center">
            {Array.from({ length: cols }).map((_, j) => (
              <Skeleton key={j} className={cn("h-5 flex-1", j === 0 ? "w-1/3" : "")} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function CardSkeleton() {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface p-6 space-y-4">
      <div className="flex justify-between items-center">
        <div className="space-y-2 flex-1">
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
        <Skeleton className="h-8 w-8 rounded-full" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    </div>
  )
}

export { Skeleton, StatCardSkeleton, TableSkeleton, CardSkeleton }
