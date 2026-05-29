/**
 * `/docs` → redirect to the first article. The docs corpus has no
 * landing/index page of its own; the sidebar IS the index.
 */
import { redirect } from "next/navigation";

export default function DocsIndex() {
  redirect("/docs/getting-started");
}
