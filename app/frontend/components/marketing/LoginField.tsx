/**
 * Labeled input field for the login form — wraps a `<label>` + `<input>`
 * pair in the `.login-field` layout from the handoff.
 *
 * Why a component instead of inlining the markup:
 *  - The same shape repeats for Email + Password (and would repeat again
 *    if we add the Magic-link form back in a follow-up PR).
 *  - Centralizes the `id` + `htmlFor` wiring so a11y stays correct even
 *    if someone copy-pastes a field.
 *  - Lets the parent pass `name`, `type`, `autoComplete`, `required`,
 *    `value`, and `onChange` without having to remember the className.
 *
 * The component is purely presentational — no internal state, the parent
 * owns the controlled-input pair. Server-renderable.
 */
import * as React from "react";

type LoginFieldProps = {
  id: string;
  name: string;
  label: string;
  type?: "email" | "password" | "text";
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  autoComplete?: string;
  required?: boolean;
  minLength?: number;
  autoFocus?: boolean;
};

export function LoginField({
  id,
  name,
  label,
  type = "text",
  value,
  onChange,
  placeholder,
  autoComplete,
  required,
  minLength,
  autoFocus,
}: LoginFieldProps) {
  return (
    <div className="login-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        name={name}
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoComplete={autoComplete}
        required={required}
        minLength={minLength}
        autoFocus={autoFocus}
      />
    </div>
  );
}
