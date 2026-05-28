/**
 * Marketing site footer (`.mk-footer`). 5-column grid + bottom bar with
 * copyright + version. Server component — no client-side state.
 *
 * Per the implementation plan, "hidden on Login" applies to the
 * route-grouped login at PR 3; this PR just builds the footer for the
 * marketing route group, so the visibility toggle is irrelevant here
 * (login lives outside the group).
 */
import Link from "next/link";

export function MarketingFooter() {
  return (
    <footer className="mk-footer" id="footer">
      <div className="container">
        <div className="mk-footer-grid">
          <div className="mk-footer-col">
            <Link href="/" className="mk-brand">
              <span className="mk-brand-mark" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <path d="M5 4 H19 V8 L12 9.5 L5 8 Z" fill="white" opacity="0.95" />
                  <path d="M11 9 H13 V20 H11 Z" fill="white" opacity="0.95" />
                </svg>
              </span>
              <span className="mk-brand-name">
                Tradenet<span className="mk-brand-tld">.vn</span>
              </span>
            </Link>
            <p className="mk-footer-tag">
              Vietnamese trademark gazette intelligence for IP professionals.
            </p>
          </div>
          <div className="mk-footer-col">
            <h4>Product</h4>
            <ul>
              <li><a href="#features">Features</a></li>
              <li><Link href="/pricing">Pricing</Link></li>
              <li><Link href="/coverage">Coverage</Link></li>
              <li><a href="#">Changelog</a></li>
              <li><Link href="/docs">API</Link></li>
            </ul>
          </div>
          <div className="mk-footer-col">
            <h4>Company</h4>
            <ul>
              <li><a href="#">About</a></li>
              <li><a href="#">Customers</a></li>
              <li><a href="#">Careers</a></li>
              <li><a href="#">Contact</a></li>
            </ul>
          </div>
          <div className="mk-footer-col">
            <h4>Resources</h4>
            <ul>
              <li><Link href="/docs">Documentation</Link></li>
              <li><Link href="/docs">Article 112 guide</Link></li>
              <li><Link href="/docs">Vienna code reference</Link></li>
              <li><a href="#">Status</a></li>
            </ul>
          </div>
          <div className="mk-footer-col">
            <h4>Legal</h4>
            <ul>
              <li><a href="#">Terms of service</a></li>
              <li><a href="#">Privacy</a></li>
              <li><a href="#">DPA</a></li>
              <li><a href="#">Security</a></li>
            </ul>
          </div>
        </div>
        <div className="mk-footer-bottom">
          <span>
            © 2026 Tradenet Pte. Ltd. · Singapore · Operating in Vietnam under license from Vietnam IP
          </span>
          <span
            className="mono"
            style={{ fontSize: 11, letterSpacing: "0.08em" }}
          >
            v 2.4.1 · Made in HCMC
          </span>
        </div>
      </div>
    </footer>
  );
}
