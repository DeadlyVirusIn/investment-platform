// Phase 2 — V2 is the only product, served at the root.
//
// The legacy Operator/quant surface (overview, labs, options, ops,
// risk, legacy/*) has been RETIRED: its routes are no longer mounted.
// The page files are intentionally retained (no deletion in this pass);
// they are simply unreferenced now and can be pruned in a later cleanup.
//
// Old /v2/* URLs (bookmarks, beta invite links) redirect to /* with the
// query string and hash preserved, so no existing link breaks.

import { Routes, Route, Navigate, useLocation } from 'react-router-dom';

import V2App from '@/v2/V2App';

// Back-compat shim: every legacy /v2/<rest> URL → /<rest>, preserving
// ?search and #hash. The "/v2/*" route only matches the /v2 prefix at a
// segment boundary, so slicing the literal "/v2" is unambiguous.
function RedirectV2ToRoot() {
  const { pathname, search, hash } = useLocation();
  const rest = pathname.slice('/v2'.length) || '/';
  return <Navigate to={`${rest}${search}${hash}`} replace />;
}

export default function App() {
  return (
    <Routes>
      {/* Back-compat: legacy /v2/* → /* (must precede the root mount). */}
      <Route path="/v2/*" element={<RedirectV2ToRoot />} />
      {/* V2 product owns the root. Its internal index redirects / → /discover
          and its own wildcard handles unknown paths. */}
      <Route path="/*" element={<V2App />} />
    </Routes>
  );
}
