import * as React from "react"
import { cn } from "@/lib/utils"
import { Inbox } from "lucide-react"

interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string
  description: string
  icon?: React.ComponentType<{ className?: string }>
  action?: React.ReactNode
}

const EmptyState = React.forwardRef<HTMLDivElement, EmptyStateProps>(
  ({ className, title, description, icon: Icon = Inbox, action, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "flex flex-col items-center justify-center text-center p-8 rounded-xl border border-dashed border-border bg-surface/30 backdrop-blur-sm",
          className
        )}
        {...props}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-elevated border border-border-subtle text-text-secondary mb-4 shadow-[0_0_15px_rgba(139,154,184,0.05)]">
          <Icon className="h-6 w-6" />
        </div>
        <h3 className="text-base font-semibold text-text-primary mb-1 font-sans">{title}</h3>
        <p className="text-sm text-text-secondary max-w-sm mb-6 font-sans leading-normal">
          {description}
        </p>
        {action && <div className="flex justify-center">{action}</div>}
      </div>
    )
  }
)
EmptyState.displayName = "EmptyState"

export { EmptyState }
