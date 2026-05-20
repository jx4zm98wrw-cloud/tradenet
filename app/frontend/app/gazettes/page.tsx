import { redirect } from "next/navigation";

/** Back-compat: the redesign moved the gazette pipeline view from /gazettes
 * to /admin/gazettes (admin-only). Anything still linking the old path hops. */
export default function LegacyGazettesPage() {
  redirect("/admin/gazettes");
}
