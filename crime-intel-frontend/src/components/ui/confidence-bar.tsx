import * as React from "react"
import { cn } from "@/lib/utils"

interface ConfidenceBarProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number // 0 to 100 or 0 to 1
  showLabel?: boolean
  size?: "sm" | "md" | "lg"
}

const ConfidenceBar = React.forwardRef<HTMLDivElement, ConfidenceBarProps>(
  ({ className, value, showLabel = true, size = "md", ...props }, ref) => {
    // Normalize value to 0-100
    const normalizedValue = Math.min(100, Math.max(0, value <= 1 && value > 0 ? value * 100 : value))
    
    let colorClass = "bg-intel-red"
    let dimColorClass = "bg-intel-red-dim/40"
    let textClass = "text-intel-red"

    if (normalizedValue >= 70) {
      colorClass = "bg-intel-green"
      dimColorClass = "bg-intel-green-dim/40"
      textClass = "text-intel-green"
    } else if (normalizedValue >= 40) {
      colorClass = "bg-intel-amber"
      dimColorClass = "bg-intel-amber-dim/40"
      textClass = "text-intel-amber"
    }

    const heightClasses = {
      sm: "h-1.5",
      md: "h-2.5",
      lg: "h-4"
    }

    return (
      <div ref={ref} className={cn("w-full flex items-center gap-3 font-mono", className)} {...props}>
        <div className="flex-1">
          <div className={cn("w-full rounded-full overflow-hidden border border-border-subtle", heightClasses[size], dimColorClass)}>
            <div
              className={cn("h-full rounded-full transition-all duration-500 ease-out", colorClass)}
              style={{ width: `${normalizedValue}%` }}
            />
          </div>
        </div>
        {showLabel && (
          <span className={cn("text-xs font-bold shrink-0 min-w-[36px] text-right", textClass)}>
            {Math.round(normalizedValue)}%
          </span>
        )}
      </div>
    )
  }
)
ConfidenceBar.displayName = "ConfidenceBar"

export { ConfidenceBar }
