import type { FC } from "react";
import { ComingSoon } from "../components/ui/ComingSoon";

export const News: FC = () => (
  <ComingSoon
    title="News"
    summary="A market-wide feed built from the NSE filings already stored per ticker — earnings, dividends, corporate actions and AGMs, with the price reaction on the day."
    phase="phase 7"
  />
);
