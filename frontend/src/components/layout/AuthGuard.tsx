import type { FC, ReactNode } from "react";
import { useAuthStore } from "../../store/useAuthStore";
import { Spinner } from "../ui/Spinner";

interface Props {
  children: ReactNode;
  fallback: ReactNode;
}

export const AuthGuard: FC<Props> = ({ children, fallback }) => {
  const { user, loading } = useAuthStore();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="relative">
        <div className="pointer-events-none select-none blur-sm opacity-40">
          {children}
        </div>
        <div className="absolute inset-0 flex items-center justify-center">
          {fallback}
        </div>
      </div>
    );
  }

  return <>{children}</>;
};
