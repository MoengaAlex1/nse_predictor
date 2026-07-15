import type { FC } from "react";
import { Link } from "react-router-dom";
import { Button } from "../ui/Button";

export const SignInPrompt: FC = () => (
  <div className="rounded-xl border border-slate-600 bg-slate-800/90 p-8 text-center backdrop-blur-sm">
    <p className="text-lg font-semibold text-slate-100">
      Sign in to unlock full analysis
    </p>
    <p className="mt-2 text-sm text-slate-400">
      Free account — AI predictions, technical indicators, risk analysis and more.
    </p>
    <div className="mt-6 flex justify-center gap-3">
      <Link to="/register">
        <Button>Create free account</Button>
      </Link>
      <Link to="/login">
        <Button variant="secondary">Sign in</Button>
      </Link>
    </div>
  </div>
);
