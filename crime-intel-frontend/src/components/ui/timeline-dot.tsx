import * as React from "react"
import { cn } from "@/lib/utils"

export type TimelineDotStatus = "compliant" | "non_compliant" | "due_soon" | "overdue" | "pending" | "general"

interface TimelineDotProps extends React.HTMLAttributes<HTMLDivElement> {
  status: TimelineDotStatus
  pulse?: boolean
  size?: "sm" | "md" | "lg"
}

const statusClasses = {
  compliant: "bg-intel-green border-intel-green/30 shadow-[0_0_8px_rgba(45,212,191,0.3)]",
  non_compliant: "bg-intel-red border-intel-red/30 shadow-[0_0_8px_rgba(244,63,94,0.3)]",
  due_soon: "bg-intel-amber border-intel-amber/30 shadow-[0_0_8px_rgba(245,158,11,0.3)]",
  overdue: "bg-intel-red border-intel-red/30 shadow-[0_0_8px_rgba(244,63,94,0.4)] animate-pulse",
  pending: "bg-border-subtle border-border/40 text-text-muted",
  general: "bg-intel-blue border-intel-blue/30 shadow-[0_0_8px_rgba(74,158,255,0.3)]"
}

const TimelineDot = React.forwardRef<HTMLDivElement, TimelineDotProps>(
  ({ className, status, pulse = false, size = "md", ...props }, ref) => {
    const sizeClass = {
      sm: "w-2 h-2",
      md: "w-3 h-3",
      lg: "w-4.5 h-4.5"
    }[size]

    return (
      <div
        ref={ref}
        className={cn(
          "rounded-full border flex items-center justify-center transition-all duration-300",
          statusClasses[status] || statusClasses.general,
          pulse && status !== "overdue" && "animate-ping opacity-75 absolute",
          sizeClass,
          className
        )}
        {...props}
      >
        {pulse && status !== "overdue" && (
          <div className={cn("rounded-full bg-current absolute opacity-40 animate-ping", sizeClass)} />
        )}
      </div>
    )
  }
)
TimelineDot.displayName = "TimelineDot"

export { TimelineDot }
