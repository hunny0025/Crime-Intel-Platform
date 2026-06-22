import * as React from "react"
import { cn } from "@/lib/utils"
import { AlertCircle, AlertTriangle, Info } from "lucide-react"

export type SeverityType = "low" | "medium" | "high"

interface SeverityIndicatorProps extends React.HTMLAttributes<HTMLDivElement> {
  severity: SeverityType
  showIcon?: boolean
  variant?: "badge" | "dot"
}

const severityConfig = {
  low: {
    border: "border-intel-blue/20 bg-intel-blue-dim/15 text-intel-blue",
    dot: "bg-intel-blue",
    icon: Info,
    label: "Low Severity"
  },
  medium: {
    border: "border-intel-amber/20 bg-intel-amber-dim/15 text-intel-amber",
    dot: "bg-intel-amber",
    icon: AlertTriangle,
    label: "Medium Severity"
  },
  high: {
    border: "border-intel-red/30 bg-intel-red-dim/20 text-intel-red animate-pulse",
    dot: "bg-intel-red",
    icon: AlertCircle,
    label: "High Severity"
  }
}

const SeverityIndicator = React.forwardRef<HTMLDivElement, SeverityIndicatorProps>(
  ({ className, severity, showIcon = true, variant = "badge", ...props }, ref) => {
    const config = severityConfig[severity] || severityConfig.low
    const Icon = config.icon

    if (variant === "dot") {
      return (
        <div ref={ref} className={cn("inline-flex items-center gap-1.5 font-sans text-xs text-text-primary", className)} {...props}>
          <span className={cn("w-2 h-2 rounded-full", config.dot)} />
          <span className="capitalize">{severity}</span>
        </div>
      )
    }

    return (
      <div
        ref={ref}
        className={cn(
          "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border text-xs font-mono font-medium select-none",
          config.border,
          className
        )}
        {...props}
      >
        {showIcon && <Icon className="w-3.5 h-3.5" />}
        <span>{config.label}</span>
      </div>
    )
  }
)
SeverityIndicator.displayName = "SeverityIndicator"

export { SeverityIndicator }
