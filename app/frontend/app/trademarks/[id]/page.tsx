import { redirect } from "next/navigation";

/** Back-compat: the redesign moved the detail view from `/trademarks/[id]` to
 * `/marks/[id]` (matches the design's URL scheme). Anything still linking the
 * old path hops to the new one. */
export default async function LegacyTrademarkPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/marks/${id}`);
}
