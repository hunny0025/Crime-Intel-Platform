import * as React from "react"
import { cn } from "@/lib/utils"

interface ProbabilityDisplayProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number // 0 to 1 or 0 to 100
  confidence?: number // 0 to 1 or 0 to 100 (optional)
  size?: "sm" | "md" | "lg"
}

const ProbabilityDisplay = React.forwardRef<HTMLDivElement, ProbabilityDisplayProps>(
  ({ className, value, confidence, size = "md", ...props }, ref) => {
    // Normalize values
    const normalizedProb = Math.min(100, Math.max(0, value <= 1 && value > 0 ? value * 100 : value))
    const normalizedConf = confidence !== undefined 
      ? Math.min(100, Math.max(0, confidence <= 1 && confidence > 0 ? confidence * 100 : confidence))
      : null

    let colorClass = "text-intel-blue"
    let bgClass = "bg-intel-blue-dim/15 border-intel-blue/20"
    let textDesc = "Likely"

    if (normalizedProb >= 80) {
      colorClass = "text-intel-magenta"
      bgClass = "bg-intel-magenta-dim/15 border-intel-magenta/20"
      textDesc = "Highly Probable"
    } else if (normalizedProb >= 60) {
      colorClass = "text-intel-purple"
      bgClass = "bg-intel-purple-dim/15 border-intel-purple/20"
      textDesc = "Probable"
    } else if (normalizedProb >= 40) {
      colorClass = "text-intel-cyan"
      bgClass = "bg-intel-cyan-dim/15 border-intel-cyan/20"
      textDesc = "Possible"
    } else if (normalizedProb >= 20) {
      colorClass = "text-intel-amber"
      bgClass = "bg-intel-amber-dim/15 border-intel-amber/20"
      textDesc = "Unlikely"
    } else {
      colorClass = "text-intel-red"
      bgClass = "bg-intel-red-dim/15 border-intel-red/20"
      textDesc = "Highly Unlikely"
    }

    const paddingClasses = {
      sm: "px-2 py-0.5 text-xs gap-1.5",
      md: "px-3 py-1.5 text-sm gap-2.5",
      lg: "px-4.5 py-2.5 text-base gap-3.5"
    }

    return (
      <div
        ref={ref}
        className={cn(
          "inline-flex items-center rounded-lg border font-mono font-bold select-none",
          bgClass,
          paddingClasses[size],
          className
        )}
        {...props}
      >
        <div className="flex flex-col">
          <div className="flex items-baseline gap-1.5">
            <span className={cn("text-lg", colorClass, size === "sm" ? "text-sm" : size === "lg" ? "text-2xl" : "text-lg")}>
              {Math.round(normalizedProb)}%
            </span>
            <span className="text-[10px] uppercase font-semibold text-text-secondary">Prob</span>
          </div>
          {normalizedConf !== null && (
            <div className="text-[9px] text-text-muted mt-0.5 leading-none">
              Conf: {Math.round(normalizedConf)}%
            </div>
          )}
        </div>
        <div className="h-6 w-px bg-border/50" />
        <span className="text-xs font-sans font-medium text-text-primary uppercase tracking-wide">
          {textDesc}
        </span>
      </div>
    )
  }
)
ProbabilityDisplay.displayName = "ProbabilityDisplay"

export { ProbabilityDisplay }
