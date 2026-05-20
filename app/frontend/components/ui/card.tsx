import * as React from "react";

type CardProps = React.HTMLAttributes<HTMLElement> & { as?: keyof React.JSX.IntrinsicElements };

export function Card({ as: As = "section", className = "", ...p }: CardProps) {
  const Tag = As as any;
  return (
    <Tag
      className={`bg-surface border border-line rounded-lg overflow-hidden ${className}`}
      {...p}
    />
  );
}

type HeadProps = {
  title?: React.ReactNode;
  sub?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
};

export function CardHead({ title, sub, action, className = "", children }: HeadProps) {
  return (
    <header className={`px-4 py-3 border-b border-line flex items-start justify-between gap-4 ${className}`}>
      {children ?? (
        <div className="min-w-0">
          {title && <h2 className="head-serif m-0 text-sm font-semibold text-ink leading-tight tracking-tight">{title}</h2>}
          {sub && <p className="mt-1 text-xs text-mute max-w-prose">{sub}</p>}
        </div>
      )}
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}

export function CardFoot({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return (
    <footer className={`px-4 py-2.5 border-t border-line flex items-center justify-between bg-paper-2 text-xs text-mute ${className}`}>
      {children}
    </footer>
  );
}

export function CardBody({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return <div className={className}>{children}</div>;
}
