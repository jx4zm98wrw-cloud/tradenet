/**
 * One source card in the "What's in the corpus" grid on `/coverage`.
 * Server component — purely structural, no client state.
 *
 * Markup mirrors `.source-card` / `.source-card.primary` from the
 * prototype (`design_handoff_tradenet_marketing/Tradenet - Marketing.html`
 * lines 717-793). Primary cards get a 2px oxblood border + stamp-2
 * gradient background via `.source-card.primary` in the marketing CSS,
 * and their pill swaps the muted paper background for `.pill-stamp`.
 */
type Kv = { dt: string; dd: string };

type Props = {
  name: string;
  sub: string;
  primary: boolean;
  pillLabel: string;
  body: string;
  /** Exactly 4 dt/dd pairs per the prototype layout. */
  kvs: ReadonlyArray<Kv>;
};

export function SourceCard({
  name,
  sub,
  primary,
  pillLabel,
  body,
  kvs,
}: Props) {
  const articleClass = primary ? "source-card primary" : "source-card";
  const pillClass = primary ? "pill pill-stamp" : "pill";
  return (
    <article className={articleClass}>
      <div className="source-card-head">
        <div>
          <h3 className="source-card-name">{name}</h3>
          <p className="source-card-sub">{sub}</p>
        </div>
        <span className={pillClass}>{pillLabel}</span>
      </div>
      <p className="source-card-body">{body}</p>
      <dl className="source-card-kv">
        {kvs.map((kv) => (
          <div key={kv.dt}>
            <dt>{kv.dt}</dt>
            <dd>{kv.dd}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}
