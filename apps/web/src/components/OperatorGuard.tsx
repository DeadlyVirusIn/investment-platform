// Sprint C — gate the operator/quant surface behind an explicit flag so a
// beginner can never wander into the operator console (labs, options, ops,
// legacy). The routes still exist; they're just unreachable without opting in.

import { Navigate, Outlet } from 'react-router-dom';
import { lsGetRaw, lsSetRaw } from '../lib/storage';

const FLAG = 'arthos_operator';

function isOperator(): boolean {
  return lsGetRaw(FLAG) === '1';
}

/** Wraps the operator route group. Non-operators are bounced to the product. */
export function OperatorGuard() {
  return isOperator() ? <Outlet /> : <Navigate to="/" replace />;
}

/** `/advanced` — opts the browser into operator mode, then enters the console. */
export function EnableOperator() {
  // lsSetRaw is defensive — if storage is unavailable, operator mode
  // simply won't persist.
  lsSetRaw(FLAG, '1');
  return <Navigate to="/overview" replace />;
}
