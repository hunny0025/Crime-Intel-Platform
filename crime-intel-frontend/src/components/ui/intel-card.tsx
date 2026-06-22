import * as React from "react"
import { cn } from "@/lib/utils"

interface IntelCardProps extends React.HTMLAttributes<HTMLDivElement> {
  glowColor?: "blue" | "green" | "amber" | "red" | "purple" | "cyan" | "magenta" | "none"
  hoverGlow?: boolean
  glass?: boolean
}

const glowColorClasses = {
  blue: "after:absolute after:inset-0 after:rounded-xl after:pointer-events-none after:border after:border-intel-blue/30 after:shadow-[0_0_15px_rgba(74,158,255,0.15)]",
  green: "after:absolute after:inset-0 after:rounded-xl after:pointer-events-none after:border after:border-intel-green/30 after:shadow-[0_0_15px_rgba(45,212,191,0.15)]",
  amber: "after:absolute after:inset-0 after:rounded-xl after:pointer-events-none after:border after:border-intel-amber/30 after:shadow-[0_0_15px_rgba(245,158,11,0.15)]",
  red: "after:absolute after:inset-0 after:rounded-xl after:pointer-events-none after:border after:border-intel-red/30 after:shadow-[0_0_15px_rgba(244,63,94,0.15)]",
  purple: "after:absolute after:inset-0 after:rounded-xl after:pointer-events-none after:border after:border-intel-purple/30 after:shadow-[0_0_15px_rgba(167,139,250,0.15)]",
  cyan: "after:absolute after:inset-0 after:rounded-xl after:pointer-events-none after:border after:border-intel-cyan/30 after:shadow-[0_0_15px_rgba(34,211,238,0.15)]",
  magenta: "after:absolute after:inset-0 after:rounded-xl after:pointer-events-none after:border after:border-intel-magenta/30 after:shadow-[0_0_15px_rgba(232,121,249,0.15)]",
  none: ""
}

const IntelCard = React.forwardRef<HTMLDivElement, IntelCardProps>(
  ({ className, glowColor = "none", hoverGlow = false, glass = false, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "rounded-xl border border-border-subtle bg-surface text-text-primary shadow-xl transition-all duration-300 relative",
          glass && "bg-surface/60 backdrop-blur-md border-border/40",
          hoverGlow && "hover:border-border/80 hover:shadow-2xl hover:translate-y-[-1px]",
          glowColor !== "none" && glowColorClasses[glowColor],
          className
        )}
        {...props}
      >
        {children}
      </div>
    )
  }
)
IntelCard.displayName = "IntelCard"

const IntelCardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("flex flex-col space-y-1.5 p-6 border-b border-border-subtle/50", className)}
      {...props}
    />
  )
)
IntelCardHeader.displayName = "IntelCardHeader"

const IntelCardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3
      ref={ref}
      className={cn("font-sans text-lg font-semibold leading-none tracking-tight text-text-primary flex items-center gap-2", className)}
      {...props}
    />
  )
)
IntelCardTitle.displayName = "IntelCardTitle"

const IntelCardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p
      ref={ref}
      className={cn("text-sm text-text-secondary font-sans", className)}
      {...props}
    />
  )
)
IntelCardDescription.displayName = "IntelCardDescription"

const IntelCardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-6 font-sans", className)} {...props} />
  )
)
IntelCardContent.displayName = "IntelCardContent"

const IntelCardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("flex items-center p-6 pt-0 border-t border-border-subtle/50 mt-6", className)}
      {...props}
    />
  )
)
IntelCardFooter.displayName = "IntelCardFooter"

export { IntelCard, IntelCardHeader, IntelCardFooter, IntelCardTitle, IntelCardDescription, IntelCardContent }
