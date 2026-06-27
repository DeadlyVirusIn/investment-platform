// Sprint C — gate the operator/quant surface behind an explicit flag so a
// beginner can never wander into the operator console (labs, options, ops,
// legacy). The routes still exist; they're just unreachable without opting in.

import { Navigate, Outlet } from 'react-router-dom';

const FLAG = 'arthos_operator';

function isOperator(): boolean {
  try {
    return localStorage.getItem(FLAG) === '1';
  } catch {
    return false;
  }
}

/** Wraps the operator route group. Non-operators are bounced to the product. */
export function OperatorGuard() {
  return isOperator() ? <Outlet /> : <Navigate to="/" replace />;
}

/** `/advanced` — opts the browser into operator mode, then enters the console. */
export function EnableOperator() {
  try {
    localStorage.setItem(FLAG, '1');
  } catch {
    /* localStorage unavailable — operator mode simply won't persist */
  }
  return <Navigate to="/overview" replace />;
}
