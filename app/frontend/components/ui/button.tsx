"use client";
import * as React from "react";
import Link from "next/link";

type Variant = "primary" | "ghost" | "tiny" | "tiny-primary";
type Size = "md" | "sm";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-stamp text-white border border-stamp-deep shadow-sm hover:bg-stamp-deep",
  ghost:
    "bg-surface text-ink-2 border border-line hover:bg-paper-2 hover:text-ink hover:border-line-strong",
  tiny:
    "bg-surface text-ink-2 border border-line hover:bg-paper-2 hover:text-ink hover:border-line-strong",
  "tiny-primary":
    "bg-stamp text-white border border-stamp-deep hover:bg-stamp-deep",
};

const SIZES: Record<Variant, string> = {
  primary: "h-8 px-3 text-[13px] rounded-md",
  ghost: "h-8 px-3 text-[13px] rounded-md",
  tiny: "h-[26px] px-2.5 text-xs rounded",
  "tiny-primary": "h-[26px] px-2.5 text-xs rounded",
};

type ButtonProps =
  & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "type">
  & {
    variant?: Variant;
    size?: Size;
    type?: "button" | "submit" | "reset";
  };

export function Button({
  variant = "ghost",
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex items-center gap-1.5 font-medium whitespace-nowrap transition disabled:opacity-50 disabled:cursor-not-allowed ${SIZES[variant]} ${VARIANTS[variant]} ${className}`}
      {...rest}
    />
  );
}

type LinkButtonProps = React.ComponentProps<typeof Link> & { className?: string };
export function LinkButton({ className = "", ...p }: LinkButtonProps) {
  return (
    <Link
      className={`inline-flex items-center gap-1 text-[12.5px] font-medium text-stamp hover:text-stamp-deep hover:underline underline-offset-2 px-1 ${className}`}
      {...p}
    />
  );
}

export function IconButton({
  title,
  className = "",
  children,
  hasDot,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { hasDot?: boolean }) {
  return (
    <button
      type="button"
      title={title}
      className={`relative w-[30px] h-[30px] rounded-md grid place-items-center text-ink-2 hover:bg-paper-2 hover:text-ink transition ${className}`}
      {...rest}
    >
      {children}
      {hasDot && (
        <span className="absolute top-1.5 right-1.5 w-[7px] h-[7px] rounded-full bg-stamp border-[1.5px] border-paper" />
      )}
    </button>
  );
}
