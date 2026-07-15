import type { FC } from "react";
import { useParams } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";

export const CompanyDeepDive: FC = () => {
  const { ticker } = useParams<{ ticker: string }>();
  return (
    <PageShell>
      <h1 className="text-3xl font-bold">{ticker}</h1>
    </PageShell>
  );
};
