/**
 * "OR" divider for the login form — sits between the SSO buttons and the
 * email/password form per the handoff design. Rendered as a line, a label,
 * and another line via CSS `::before`/`::after` pseudo-elements in
 * `marketing.css` (`.login-divider`).
 *
 * Purely presentational — no props, no client state. Lives in
 * `components/marketing/` alongside the other login-specific marketing
 * components even though the `/login` route is outside the `(marketing)`
 * Route Group, because these components were designed *for* the marketing
 * handoff and would be confusing if scattered.
 */
export function LoginDivider() {
  return <div className="login-divider">or</div>;
}
