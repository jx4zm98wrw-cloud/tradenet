/**
 * In-page "On this page" table of contents.
 *
 * Server component. Renders a small box with a label and an ordered list
 * of anchor links to in-page section IDs.
 */
type TocItem = { href: string; label: string };

type Props = {
  items: ReadonlyArray<TocItem>;
};

export function DocsTOC({ items }: Props) {
  return (
    <div className="docs-toc">
      <div className="docs-toc-label">On this page</div>
      <ol>
        {items.map((item) => (
          <li key={item.href}>
            <a href={item.href}>{item.label}</a>
          </li>
        ))}
      </ol>
    </div>
  );
}
