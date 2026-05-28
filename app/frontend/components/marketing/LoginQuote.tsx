/**
 * Pull-quote that anchors the bottom of the login left pane. Big serif
 * quote mark, italicized-feeling testimonial body (rendered in Source
 * Serif 4 medium per the handoff), then a mono-style byline.
 *
 * The content is hard-coded to a single quote per the prototype — when
 * we have real customer testimonials, swap the props in from a CMS or
 * a typed copy module like `_content/landing.ts`.
 *
 * Server component — purely structural markup, no client state.
 */
type LoginQuoteProps = {
  /** The body of the quote (without surrounding quote marks). */
  text: string;
  /** Attribution byline — `name` bolded, `role` muted. */
  attribution: { name: string; role: string };
};

export function LoginQuote({ text, attribution }: LoginQuoteProps) {
  return (
    <div className="login-quote">
      <span className="login-quote-mark" aria-hidden="true">
        &ldquo;
      </span>
      <p className="login-quote-text">{text}</p>
      <p className="login-quote-author">
        <strong>{attribution.name}</strong> · {attribution.role}
      </p>
    </div>
  );
}
