import * as React from "react"
import { cn } from "@/lib/utils"
import { ArrowUpRight, ArrowDownRight, Minus } from "lucide-react"

interface StatCardProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string
  value: string | number
  subtext?: string
  trend?: {
    value: string | number
    direction: "up" | "down" | "neutral"
  }
  icon?: React.ComponentType<{ className?: string }>
}

const StatCard = React.forwardRef<HTMLDivElement, StatCardProps>(
  ({ className, title, value, subtext, trend, icon: Icon, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "rounded-xl border border-border-subtle bg-surface p-6 shadow-lg transition-all duration-300 hover:border-border/60 hover:shadow-xl",
          className
        )}
        {...props}
      >
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono font-bold uppercase tracking-wider text-text-secondary">
            {title}
          </span>
          {Icon && (
            <div className="h-8 w-8 rounded-lg bg-elevated border border-border-subtle flex items-center justify-center text-text-secondary shadow-inner">
              <Icon className="h-4.5 w-4.5" />
            </div>
          )}
        </div>
        <div className="mt-4 flex items-baseline justify-between gap-2">
          <span className="text-2xl font-bold font-mono tracking-tight text-text-primary">
            {value}
          </span>
          {trend && (
            <div
              className={cn(
                "inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-xs font-mono font-bold",
                trend.direction === "up" && "bg-intel-green-dim/15 text-intel-green border border-intel-green/20",
                trend.direction === "down" && "bg-intel-red-dim/15 text-intel-red border border-intel-red/20",
                trend.direction === "neutral" && "bg-elevated text-text-secondary border border-border-subtle"
              )}
            >
              {trend.direction === "up" && <ArrowUpRight className="h-3 w-3" />}
              {trend.direction === "down" && <ArrowDownRight className="h-3 w-3" />}
              {trend.direction === "neutral" && <Minus className="h-3 w-3" />}
              <span>{trend.value}</span>
            </div>
          )}
        </div>
        {subtext && (
          <p className="mt-2 text-xs text-text-muted font-sans leading-normal">
            {subtext}
          </p>
        )}
      </div>
    )
  }
)
StatCard.displayName = "StatCard"

export { StatCard }
