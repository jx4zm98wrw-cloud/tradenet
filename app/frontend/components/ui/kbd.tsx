export function Kbd({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd
      className={`font-mono text-[10.5px] bg-paper-2 border border-line rounded px-1.5 py-0.5 text-mute leading-none ${className}`}
    >
      {children}
    </kbd>
  );
}
