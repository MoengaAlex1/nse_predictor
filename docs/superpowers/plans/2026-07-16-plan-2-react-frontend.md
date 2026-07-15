# NSE Web Platform — Plan 2: React Frontend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full React frontend for the NSE Market Intelligence Platform — scaffold through deployed Cloudflare Pages app with Home, Companies list, Company deep dive (public + gated), and Login/Register pages.

**Architecture:** Vite + React 18 + TypeScript SPA living in `frontend/` at the repo root. Firebase JS SDK reads pre-computed data from Firestore; Zustand holds auth state; TanStack Query handles all Firestore fetching with caching. Tailwind CSS dark theme throughout. Recharts for all charts. Cloudflare Pages serves the built SPA via Wrangler in GitHub Actions.

**Tech Stack:** React 18, TypeScript 5, Vite 5, Tailwind CSS 3, Recharts 2, Firebase JS SDK 10, React Router 6, Zustand 4, TanStack Query 5, Vitest 1, @testing-library/react 14

---

## Firestore collection reference (from Plan 1)

All data is written by the Python pipeline. Document IDs use safe tickers (`SCOM_NR`, not `SCOM.NR`):

| Collection | Access | Key fields |
|---|---|---|
| `companies/{safe_ticker}` | Public | `id` (doc ID = safe ticker), `ticker` (original e.g. `SCOM.NR`), `name`, `short`, `sector`, `color`, `icon`, `current_price`, `change_pct_today`, `signal`, `price_preview[30]`, `last_updated` |
| `companies/{safe_ticker}/snapshots/{YYYY-MM-DD}` | Auth-gated | `signal`, `risk_adjusted_signal`, `current_price_KES`, `predicted_price_KES`, `predicted_change_pct`, `var_95_pct`, `rationale`, `metrics{rmse,mae,mape,directional_accuracy}`, `actuals[]`, `preds[]`, `forecast[30]` |
| `companies/{safe_ticker}/technicals/{YYYY-MM-DD}` | Auth-gated | `rsi_14`, `macd`, `sma_20`, `sma_50`, `sma_200`, `ema_12`, `ema_26`, `volume`, `avg_volume_30d`, `daily_return`, `volatility_30d`, `monthly_heatmap` |
| `market_overview/{YYYY-MM-DD}` | Public | `top_gainers[]`, `top_losers[]`, `signal_distribution`, `sector_performance`, `nse20_value`, `nse20_change_pct` |

The `id` field on CompanyDoc is the Firestore document ID (safe ticker). Frontend routes use the safe ticker: `/company/SCOM_NR`.

---

## File Map

```
frontend/
├── .env.example                          ← Firebase client env var template
├── index.html                            ← dark class on <html>
├── package.json
├── postcss.config.js
├── tailwind.config.ts
├── vite.config.ts                        ← also configures Vitest
├── src/
│   ├── index.css                         ← @tailwind directives
│   ├── test-setup.ts                     ← @testing-library/jest-dom import
│   ├── main.tsx                          ← BrowserRouter + QueryClientProvider
│   ├── App.tsx                           ← Routes + auth listener
│   ├── types/
│   │   └── index.ts                      ← CompanyDoc, SnapshotDoc, TechnicalsDoc, MarketOverviewDoc
│   ├── lib/
│   │   ├── firebase.ts                   ← initializeApp, getFirestore, getAuth
│   │   ├── firestore.ts                  ← fetchAllCompanies, fetchCompany, fetchLatestSnapshot, fetchLatestTechnicals, fetchMarketOverview
│   │   └── auth.ts                       ← loginWithEmail, registerWithEmail, loginWithGoogle, logout, initAuthListener
│   ├── store/
│   │   └── useAuthStore.ts               ← Zustand: { user, loading, setUser, setLoading }
│   ├── hooks/
│   │   ├── useCompanies.ts               ← useCompanies()
│   │   ├── useCompany.ts                 ← useCompany(ticker), useLatestSnapshot(ticker), useLatestTechnicals(ticker)
│   │   └── useMarket.ts                  ← useMarketOverview()
│   ├── components/
│   │   ├── ui/
│   │   │   ├── Badge.tsx                 ← SignalBadge
│   │   │   ├── Badge.test.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Spinner.tsx
│   │   │   └── Button.tsx
│   │   ├── charts/
│   │   │   ├── SparkLine.tsx             ← 30-day price preview
│   │   │   └── PredictionChart.tsx       ← actual vs predicted vs forecast
│   │   ├── company/
│   │   │   └── SignInPrompt.tsx          ← blurred-overlay CTA
│   │   └── layout/
│   │       ├── Navbar.tsx
│   │       ├── PageShell.tsx             ← Navbar + max-w-7xl wrapper
│   │       ├── AuthGuard.tsx             ← blurs children, shows fallback when logged out
│   │       └── AuthGuard.test.tsx
│   └── pages/
│       ├── Home.tsx                      ← market overview: gainers/losers/signal strip
│       ├── Companies.tsx                 ← searchable/filterable company grid
│       ├── Companies.test.tsx
│       ├── CompanyDeepDive.tsx           ← public header + gated deep dive
│       ├── Login.tsx
│       └── Register.tsx
```

---

## Task 1: Vite scaffold + Tailwind CSS + Vitest

**Files:**
- Create: `frontend/` (Vite scaffold)
- Modify: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Modify: `frontend/src/index.css`
- Modify: `frontend/index.html`
- Create: `frontend/src/test-setup.ts`

- [ ] **Step 1: Scaffold Vite + React 18 + TypeScript**

From repo root `C:\Users\moeng\nse_predictor`:

```powershell
npm create vite@latest frontend -- --template react-ts
```

Then install base deps:

```powershell
cd frontend
npm install
```

- [ ] **Step 2: Install all additional dependencies**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npm install react-router-dom@6 zustand @tanstack/react-query firebase recharts
npm install -D tailwindcss@3 postcss autoprefixer vitest @vitest/coverage-v8 @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 3: Write `frontend/tailwind.config.ts`**

```typescript
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
```

- [ ] **Step 4: Write `frontend/postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Replace `frontend/src/index.css`**

Delete all existing content and write:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 6: Update `frontend/index.html`** — add `class="dark"` to `<html>`

```html
<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>NSE Intelligence</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Update `frontend/vite.config.ts`** — add Vitest config

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
```

- [ ] **Step 8: Create `frontend/src/test-setup.ts`**

```typescript
import "@testing-library/jest-dom";
```

- [ ] **Step 9: Add Vitest types to `tsconfig.app.json`**

Find the `"compilerOptions"` block in `frontend/tsconfig.app.json` and add `"types": ["vitest/globals"]`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals"]
  },
  "include": ["src"]
}
```

If your scaffold created `tsconfig.json` without `tsconfig.app.json`, add `"types": ["vitest/globals"]` to the `compilerOptions` in `tsconfig.json` instead.

- [ ] **Step 10: Write a smoke test to verify the setup works**

Create `frontend/src/App.test.tsx`:

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

describe("scaffold smoke test", () => {
  it("renders a div", () => {
    render(<div data-testid="smoke">ok</div>);
    expect(screen.getByTestId("smoke")).toBeInTheDocument();
  });
});
```

- [ ] **Step 11: Run the smoke test — expect PASS**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx vitest run
```

Expected:
```
✓ src/App.test.tsx > scaffold smoke test > renders a div
1 passed
```

- [ ] **Step 12: Verify dev server starts**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npm run build 2>&1 | Select-Object -Last 5
```

Expected: `✓ built in` with no errors. (TypeScript may warn about missing firebase env vars — that's OK at this stage.)

- [ ] **Step 13: Delete the smoke test and commit**

Delete `frontend/src/App.test.tsx`, then:

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/
git commit -m "feat: scaffold React 18 + TypeScript + Tailwind + Vitest frontend"
```

---

## Task 2: TypeScript types + Firebase config + env template

**Files:**
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/lib/firebase.ts`
- Create: `frontend/.env.example`

- [ ] **Step 1: Write `frontend/src/types/index.ts`**

```typescript
export interface CompanyDoc {
  id: string;
  ticker: string;
  name: string;
  short: string;
  sector: string;
  color: string;
  icon: string;
  csv: string;
  current_price: number | null;
  change_pct_today: number | null;
  signal: "BUY" | "HOLD" | "SELL" | null;
  price_preview: number[];
  last_updated: string | null;
}

export interface SnapshotDoc {
  signal: "BUY" | "HOLD" | "SELL";
  risk_adjusted_signal: "BUY" | "HOLD" | "SELL";
  current_price_KES: number;
  predicted_price_KES: number;
  predicted_change_pct: number;
  var_95_pct: number;
  rationale: string;
  metrics: {
    rmse: number;
    mae: number;
    mape: number;
    directional_accuracy: number;
  };
  actuals: number[];
  preds: number[];
  forecast: number[];
}

export interface TechnicalsDoc {
  date: string;
  rsi_14: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  bb_upper: number | null;
  bb_mid: number | null;
  bb_lower: number | null;
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
  ema_12: number | null;
  ema_26: number | null;
  volume: number;
  avg_volume_30d: number;
  daily_return: number | null;
  volatility_30d: number | null;
  monthly_heatmap: Record<string, number>;
}

export interface MarketOverviewDoc {
  date: string;
  top_gainers: { ticker: string; change_pct: number }[];
  top_losers: { ticker: string; change_pct: number }[];
  signal_distribution: { BUY: number; HOLD: number; SELL: number };
  sector_performance: Record<string, number>;
  nse20_value: number | null;
  nse20_change_pct: number | null;
}
```

- [ ] **Step 2: Write `frontend/.env.example`**

```
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
```

- [ ] **Step 3: Write `frontend/src/lib/firebase.ts`**

```typescript
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

export const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
export const auth = getAuth(app);
```

- [ ] **Step 4: Verify TypeScript compiles with no errors**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx tsc --noEmit 2>&1
```

Expected: no output (no errors). Ignore warnings about missing env var values.

- [ ] **Step 5: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/types/ frontend/src/lib/firebase.ts frontend/.env.example
git commit -m "feat: add TypeScript types, Firebase config, and env template"
```

---

## Task 3: Zustand auth store + Firebase Auth helpers

**Files:**
- Create: `frontend/src/store/useAuthStore.ts`
- Create: `frontend/src/lib/auth.ts`

- [ ] **Step 1: Write `frontend/src/store/useAuthStore.ts`**

```typescript
import { create } from "zustand";
import type { User } from "firebase/auth";

interface AuthState {
  user: User | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  setLoading: (loading: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  setUser: (user) => set({ user, loading: false }),
  setLoading: (loading) => set({ loading }),
}));
```

- [ ] **Step 2: Write `frontend/src/lib/auth.ts`**

```typescript
import {
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider,
  signOut,
  onAuthStateChanged,
  type User,
} from "firebase/auth";
import { doc, setDoc, serverTimestamp } from "firebase/firestore";
import { auth, db } from "./firebase";
import { useAuthStore } from "../store/useAuthStore";

const googleProvider = new GoogleAuthProvider();

export async function loginWithEmail(email: string, password: string): Promise<void> {
  await signInWithEmailAndPassword(auth, email, password);
}

export async function registerWithEmail(email: string, password: string): Promise<void> {
  const cred = await createUserWithEmailAndPassword(auth, email, password);
  await createUserDoc(cred.user);
}

export async function loginWithGoogle(): Promise<void> {
  const cred = await signInWithPopup(auth, googleProvider);
  await createUserDoc(cred.user);
}

export async function logout(): Promise<void> {
  await signOut(auth);
}

async function createUserDoc(user: User): Promise<void> {
  const ref = doc(db, "users", user.uid);
  await setDoc(
    ref,
    { watchlist: [], plan: "free", created_at: serverTimestamp() },
    { merge: true }
  );
}

export function initAuthListener(): () => void {
  return onAuthStateChanged(auth, (user) => {
    useAuthStore.getState().setUser(user);
  });
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 4: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/store/ frontend/src/lib/auth.ts
git commit -m "feat: add Zustand auth store and Firebase Auth helpers"
```

---

## Task 4: Firestore query helpers + TanStack Query hooks

**Files:**
- Create: `frontend/src/lib/firestore.ts`
- Create: `frontend/src/hooks/useCompanies.ts`
- Create: `frontend/src/hooks/useCompany.ts`
- Create: `frontend/src/hooks/useMarket.ts`

- [ ] **Step 1: Write `frontend/src/lib/firestore.ts`**

```typescript
import {
  collection,
  doc,
  getDoc,
  getDocs,
  query,
  orderBy,
  limit,
} from "firebase/firestore";
import { db } from "./firebase";
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc, MarketOverviewDoc } from "../types";

export async function fetchAllCompanies(): Promise<CompanyDoc[]> {
  const snap = await getDocs(collection(db, "companies"));
  return snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<CompanyDoc, "id">) }));
}

export async function fetchCompany(safeTicker: string): Promise<CompanyDoc | null> {
  const ref = doc(db, "companies", safeTicker);
  const snap = await getDoc(ref);
  if (!snap.exists()) return null;
  return { id: snap.id, ...(snap.data() as Omit<CompanyDoc, "id">) };
}

export async function fetchLatestSnapshot(safeTicker: string): Promise<SnapshotDoc | null> {
  const ref = collection(db, "companies", safeTicker, "snapshots");
  const q = query(ref, orderBy("__name__", "desc"), limit(1));
  const snap = await getDocs(q);
  if (snap.empty) return null;
  return snap.docs[0].data() as SnapshotDoc;
}

export async function fetchLatestTechnicals(safeTicker: string): Promise<TechnicalsDoc | null> {
  const ref = collection(db, "companies", safeTicker, "technicals");
  const q = query(ref, orderBy("__name__", "desc"), limit(1));
  const snap = await getDocs(q);
  if (snap.empty) return null;
  return snap.docs[0].data() as TechnicalsDoc;
}

export async function fetchMarketOverview(): Promise<MarketOverviewDoc | null> {
  const ref = collection(db, "market_overview");
  const q = query(ref, orderBy("__name__", "desc"), limit(1));
  const snap = await getDocs(q);
  if (snap.empty) return null;
  return snap.docs[0].data() as MarketOverviewDoc;
}
```

- [ ] **Step 2: Write `frontend/src/hooks/useCompanies.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { fetchAllCompanies } from "../lib/firestore";
import type { CompanyDoc } from "../types";

export function useCompanies() {
  return useQuery<CompanyDoc[]>({
    queryKey: ["companies"],
    queryFn: fetchAllCompanies,
    staleTime: 5 * 60 * 1000,
  });
}
```

- [ ] **Step 3: Write `frontend/src/hooks/useCompany.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { fetchCompany, fetchLatestSnapshot, fetchLatestTechnicals } from "../lib/firestore";
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc } from "../types";

export function useCompany(safeTicker: string) {
  return useQuery<CompanyDoc | null>({
    queryKey: ["company", safeTicker],
    queryFn: () => fetchCompany(safeTicker),
    enabled: !!safeTicker,
  });
}

export function useLatestSnapshot(safeTicker: string, enabled = true) {
  return useQuery<SnapshotDoc | null>({
    queryKey: ["snapshot", safeTicker],
    queryFn: () => fetchLatestSnapshot(safeTicker),
    enabled: !!safeTicker && enabled,
  });
}

export function useLatestTechnicals(safeTicker: string, enabled = true) {
  return useQuery<TechnicalsDoc | null>({
    queryKey: ["technicals", safeTicker],
    queryFn: () => fetchLatestTechnicals(safeTicker),
    enabled: !!safeTicker && enabled,
  });
}
```

- [ ] **Step 4: Write `frontend/src/hooks/useMarket.ts`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { fetchMarketOverview } from "../lib/firestore";
import type { MarketOverviewDoc } from "../types";

export function useMarketOverview() {
  return useQuery<MarketOverviewDoc | null>({
    queryKey: ["market_overview"],
    queryFn: fetchMarketOverview,
    staleTime: 5 * 60 * 1000,
  });
}
```

- [ ] **Step 5: Verify TypeScript compiles**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 6: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/lib/firestore.ts frontend/src/hooks/
git commit -m "feat: add Firestore query helpers and TanStack Query hooks"
```

---

## Task 5: UI primitives (SignalBadge, Card, Spinner, Button)

**Files:**
- Create: `frontend/src/components/ui/Badge.tsx`
- Create: `frontend/src/components/ui/Badge.test.tsx`
- Create: `frontend/src/components/ui/Card.tsx`
- Create: `frontend/src/components/ui/Spinner.tsx`
- Create: `frontend/src/components/ui/Button.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ui/Badge.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { SignalBadge } from "./Badge";

describe("SignalBadge", () => {
  it("renders BUY text", () => {
    render(<SignalBadge signal="BUY" />);
    expect(screen.getByText("BUY")).toBeInTheDocument();
  });

  it("renders HOLD text", () => {
    render(<SignalBadge signal="HOLD" />);
    expect(screen.getByText("HOLD")).toBeInTheDocument();
  });

  it("renders SELL text", () => {
    render(<SignalBadge signal="SELL" />);
    expect(screen.getByText("SELL")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect ImportError**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx vitest run src/components/ui/Badge.test.tsx
```

Expected: `Cannot find module './Badge'`

- [ ] **Step 3: Write `frontend/src/components/ui/Badge.tsx`**

```typescript
import type { FC } from "react";

const signalColors: Record<string, string> = {
  BUY: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  HOLD: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  SELL: "bg-red-500/20 text-red-400 border-red-500/30",
};

interface Props {
  signal: "BUY" | "HOLD" | "SELL";
  size?: "sm" | "lg";
}

export const SignalBadge: FC<Props> = ({ signal, size = "sm" }) => {
  const px =
    size === "lg"
      ? "px-4 py-2 text-sm font-bold"
      : "px-2 py-0.5 text-xs font-semibold";
  return (
    <span
      className={`inline-flex items-center rounded-full border ${px} ${signalColors[signal] ?? ""}`}
    >
      {signal}
    </span>
  );
};
```

- [ ] **Step 4: Run test — expect 3 PASS**

```powershell
npx vitest run src/components/ui/Badge.test.tsx
```

Expected: `3 passed`

- [ ] **Step 5: Write `frontend/src/components/ui/Card.tsx`**

```typescript
import type { FC, ReactNode } from "react";

interface Props {
  children: ReactNode;
  className?: string;
}

export const Card: FC<Props> = ({ children, className = "" }) => (
  <div className={`rounded-xl bg-slate-800 border border-slate-700 p-4 ${className}`}>
    {children}
  </div>
);
```

- [ ] **Step 6: Write `frontend/src/components/ui/Spinner.tsx`**

```typescript
import type { FC } from "react";

const sizes = { sm: "h-4 w-4", md: "h-8 w-8", lg: "h-12 w-12" };

export const Spinner: FC<{ size?: "sm" | "md" | "lg" }> = ({ size = "md" }) => (
  <div
    className={`${sizes[size]} animate-spin rounded-full border-2 border-slate-600 border-t-sky-400`}
  />
);
```

- [ ] **Step 7: Write `frontend/src/components/ui/Button.tsx`**

```typescript
import type { FC, ReactNode, ButtonHTMLAttributes } from "react";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}

const variants = {
  primary: "bg-sky-500 hover:bg-sky-400 text-white",
  secondary: "bg-slate-700 hover:bg-slate-600 text-slate-200",
  ghost: "hover:bg-slate-700 text-slate-400 hover:text-slate-200",
};

const sizes = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

export const Button: FC<Props> = ({
  variant = "primary",
  size = "md",
  children,
  className = "",
  ...rest
}) => (
  <button
    className={`inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-sky-400 disabled:opacity-50 disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]} ${className}`}
    {...rest}
  >
    {children}
  </button>
);
```

- [ ] **Step 8: Run full test suite — expect 3 PASS**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx vitest run
```

Expected: `3 passed` (Badge tests)

- [ ] **Step 9: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/components/ui/
git commit -m "feat: add UI primitives — SignalBadge, Card, Spinner, Button"
```

---

## Task 6: Chart components (SparkLine, PredictionChart)

**Files:**
- Create: `frontend/src/components/charts/SparkLine.tsx`
- Create: `frontend/src/components/charts/PredictionChart.tsx`

No tests for chart components — Recharts renders SVG and is hard to unit test meaningfully. Visual verification is done when the dev server is running.

- [ ] **Step 1: Write `frontend/src/components/charts/SparkLine.tsx`**

```typescript
import type { FC } from "react";
import { LineChart, Line, ResponsiveContainer, Tooltip } from "recharts";

interface Props {
  data: number[];
  color: string;
}

export const SparkLine: FC<Props> = ({ data, color }) => {
  const chartData = data.map((v, i) => ({ i, v }));
  return (
    <ResponsiveContainer width="100%" height={80}>
      <LineChart data={chartData}>
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} />
        <Tooltip
          contentStyle={{
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelFormatter={() => ""}
          formatter={(v: number) => [`KES ${v.toFixed(2)}`, "Price"]}
        />
      </LineChart>
    </ResponsiveContainer>
  );
};
```

- [ ] **Step 2: Write `frontend/src/components/charts/PredictionChart.tsx`**

```typescript
import type { FC } from "react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface Props {
  actuals: number[];
  preds: number[];
  forecast: number[];
}

export const PredictionChart: FC<Props> = ({ actuals, preds, forecast }) => {
  const n = Math.min(actuals.length, preds.length);

  const histData = Array.from({ length: n }, (_, i) => ({
    i,
    actual: actuals[i],
    predicted: preds[i],
  }));

  const forecastData = forecast.map((v, i) => ({
    i: n + i,
    forecast: v,
    actual: undefined,
    predicted: undefined,
  }));

  const allData = [...histData, ...forecastData];

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={allData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis dataKey="i" tick={false} />
        <YAxis
          tickFormatter={(v: number) => v.toFixed(0)}
          tick={{ fill: "#94a3b8", fontSize: 11 }}
          width={55}
        />
        <Tooltip
          contentStyle={{
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
            fontSize: 12,
          }}
          formatter={(v: number, name: string) => [
            `KES ${v?.toFixed(2) ?? "—"}`,
            name,
          ]}
        />
        <Legend />
        <Line
          type="monotone"
          dataKey="actual"
          stroke="#38bdf8"
          strokeWidth={2}
          dot={false}
          name="Actual"
        />
        <Line
          type="monotone"
          dataKey="predicted"
          stroke="#a78bfa"
          strokeWidth={2}
          dot={false}
          strokeDasharray="4 2"
          name="Predicted"
        />
        <Area
          type="monotone"
          dataKey="forecast"
          stroke="#34d399"
          fill="#34d39920"
          strokeWidth={2}
          dot={false}
          name="Forecast"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
};
```

- [ ] **Step 3: Verify TypeScript compiles**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 4: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/components/charts/
git commit -m "feat: add SparkLine and PredictionChart Recharts components"
```

---

## Task 7: Layout components (Navbar, PageShell, AuthGuard, SignInPrompt)

**Files:**
- Create: `frontend/src/components/layout/AuthGuard.tsx`
- Create: `frontend/src/components/layout/AuthGuard.test.tsx`
- Create: `frontend/src/components/layout/Navbar.tsx`
- Create: `frontend/src/components/layout/PageShell.tsx`
- Create: `frontend/src/components/company/SignInPrompt.tsx`

- [ ] **Step 1: Write the failing AuthGuard test**

Create `frontend/src/components/layout/AuthGuard.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { AuthGuard } from "./AuthGuard";
import * as storeModule from "../../store/useAuthStore";

vi.mock("../../store/useAuthStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = vi.mocked(storeModule.useAuthStore);

describe("AuthGuard", () => {
  it("shows spinner when loading, not children or fallback", () => {
    mockUseAuthStore.mockReturnValue({
      user: null,
      loading: true,
      setUser: vi.fn(),
      setLoading: vi.fn(),
    } as any);
    render(
      <AuthGuard fallback={<div>Sign in</div>}>
        <div>Protected content</div>
      </AuthGuard>
    );
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    expect(screen.queryByText("Sign in")).not.toBeInTheDocument();
  });

  it("shows fallback when logged out", () => {
    mockUseAuthStore.mockReturnValue({
      user: null,
      loading: false,
      setUser: vi.fn(),
      setLoading: vi.fn(),
    } as any);
    render(
      <AuthGuard fallback={<div>Sign in</div>}>
        <div>Protected content</div>
      </AuthGuard>
    );
    expect(screen.getByText("Sign in")).toBeInTheDocument();
  });

  it("shows children when authenticated", () => {
    mockUseAuthStore.mockReturnValue({
      user: { uid: "abc" } as any,
      loading: false,
      setUser: vi.fn(),
      setLoading: vi.fn(),
    } as any);
    render(
      <AuthGuard fallback={<div>Sign in</div>}>
        <div>Protected content</div>
      </AuthGuard>
    );
    expect(screen.getByText("Protected content")).toBeInTheDocument();
    expect(screen.queryByText("Sign in")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect ImportError**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx vitest run src/components/layout/AuthGuard.test.tsx
```

Expected: `Cannot find module './AuthGuard'`

- [ ] **Step 3: Write `frontend/src/components/layout/AuthGuard.tsx`**

```typescript
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
```

- [ ] **Step 4: Run AuthGuard tests — expect 3 PASS**

```powershell
npx vitest run src/components/layout/AuthGuard.test.tsx
```

Expected: `3 passed`

- [ ] **Step 5: Write `frontend/src/components/layout/Navbar.tsx`**

```typescript
import type { FC } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/useAuthStore";
import { logout } from "../../lib/auth";
import { Button } from "../ui/Button";

export const Navbar: FC = () => {
  const { user } = useAuthStore();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/");
  }

  return (
    <nav className="border-b border-slate-700 bg-slate-900">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="text-lg font-bold text-sky-400">
              NSE Intelligence
            </Link>
            <Link
              to="/companies"
              className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
            >
              Companies
            </Link>
            {user && (
              <Link
                to="/market"
                className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
              >
                Market
              </Link>
            )}
          </div>
          <div className="flex items-center gap-3">
            {user ? (
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                Sign out
              </Button>
            ) : (
              <>
                <Link to="/login">
                  <Button variant="ghost" size="sm">Sign in</Button>
                </Link>
                <Link to="/register">
                  <Button size="sm">Get started free</Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
};
```

- [ ] **Step 6: Write `frontend/src/components/layout/PageShell.tsx`**

```typescript
import type { FC, ReactNode } from "react";
import { Navbar } from "./Navbar";

export const PageShell: FC<{ children: ReactNode }> = ({ children }) => (
  <div className="min-h-screen bg-slate-950 text-slate-100">
    <Navbar />
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">{children}</main>
  </div>
);
```

- [ ] **Step 7: Write `frontend/src/components/company/SignInPrompt.tsx`**

```typescript
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
```

- [ ] **Step 8: Run full test suite — expect 6 PASS (3 Badge + 3 AuthGuard)**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx vitest run
```

Expected: `6 passed`

- [ ] **Step 9: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/components/layout/ frontend/src/components/company/
git commit -m "feat: add layout components — Navbar, PageShell, AuthGuard, SignInPrompt"
```

---

## Task 8: React Router + App.tsx + main.tsx

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`
- Create: `frontend/src/pages/Home.tsx` (placeholder)
- Create: `frontend/src/pages/Companies.tsx` (placeholder)
- Create: `frontend/src/pages/CompanyDeepDive.tsx` (placeholder)
- Create: `frontend/src/pages/Login.tsx` (placeholder)
- Create: `frontend/src/pages/Register.tsx` (placeholder)

- [ ] **Step 1: Create placeholder page files**

Create `frontend/src/pages/Home.tsx`:

```typescript
import type { FC } from "react";
import { PageShell } from "../components/layout/PageShell";

export const Home: FC = () => (
  <PageShell>
    <h1 className="text-3xl font-bold">Home</h1>
  </PageShell>
);
```

Create `frontend/src/pages/Companies.tsx`:

```typescript
import type { FC } from "react";
import { PageShell } from "../components/layout/PageShell";

export const Companies: FC = () => (
  <PageShell>
    <h1 className="text-3xl font-bold">Companies</h1>
  </PageShell>
);
```

Create `frontend/src/pages/CompanyDeepDive.tsx`:

```typescript
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
```

Create `frontend/src/pages/Login.tsx`:

```typescript
import type { FC } from "react";
import { PageShell } from "../components/layout/PageShell";

export const Login: FC = () => (
  <PageShell>
    <h1 className="text-3xl font-bold">Login</h1>
  </PageShell>
);
```

Create `frontend/src/pages/Register.tsx`:

```typescript
import type { FC } from "react";
import { PageShell } from "../components/layout/PageShell";

export const Register: FC = () => (
  <PageShell>
    <h1 className="text-3xl font-bold">Register</h1>
  </PageShell>
);
```

- [ ] **Step 2: Write `frontend/src/App.tsx`**

```typescript
import { useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import { initAuthListener } from "./lib/auth";
import { Home } from "./pages/Home";
import { Companies } from "./pages/Companies";
import { CompanyDeepDive } from "./pages/CompanyDeepDive";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";

export default function App() {
  useEffect(() => {
    const unsubscribe = initAuthListener();
    return unsubscribe;
  }, []);

  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/companies" element={<Companies />} />
      <Route path="/company/:ticker" element={<CompanyDeepDive />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
    </Routes>
  );
}
```

- [ ] **Step 3: Write `frontend/src/main.tsx`**

```typescript
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, retry: 1 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>
);
```

- [ ] **Step 4: Verify TypeScript compiles**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 5: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/App.tsx frontend/src/main.tsx frontend/src/pages/
git commit -m "feat: wire React Router routes and providers in App.tsx and main.tsx"
```

---

## Task 9: Home page

**Files:**
- Modify: `frontend/src/pages/Home.tsx` (replace placeholder)

- [ ] **Step 1: Replace `frontend/src/pages/Home.tsx` with full implementation**

```typescript
import type { FC } from "react";
import { Link } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { SignalBadge } from "../components/ui/Badge";
import { useMarketOverview } from "../hooks/useMarket";

export const Home: FC = () => {
  const { data: market, isLoading, isError } = useMarketOverview();

  return (
    <PageShell>
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-100">NSE Market Overview</h1>
          <p className="mt-1 text-slate-400">
            Nairobi Securities Exchange — AI-powered analytics
          </p>
        </div>

        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <Spinner size="lg" />
          </div>
        )}

        {isError && (
          <Card className="border-red-800 bg-red-950/20">
            <p className="text-red-400">Failed to load market data. Please try again.</p>
          </Card>
        )}

        {market && (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <Card>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
                Signal Distribution
              </h2>
              <div className="flex gap-6">
                <div className="text-center">
                  <p className="text-2xl font-bold text-emerald-400">
                    {market.signal_distribution.BUY}
                  </p>
                  <SignalBadge signal="BUY" />
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-amber-400">
                    {market.signal_distribution.HOLD}
                  </p>
                  <SignalBadge signal="HOLD" />
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-red-400">
                    {market.signal_distribution.SELL}
                  </p>
                  <SignalBadge signal="SELL" />
                </div>
              </div>
            </Card>

            <Card>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
                Top Gainers
              </h2>
              <ul className="space-y-2">
                {market.top_gainers.slice(0, 3).map((g) => (
                  <li key={g.ticker} className="flex items-center justify-between">
                    <Link
                      to={`/company/${g.ticker}`}
                      className="text-sm font-medium text-slate-200 hover:text-sky-400"
                    >
                      {g.ticker}
                    </Link>
                    <span className="text-sm font-medium text-emerald-400">
                      +{g.change_pct.toFixed(2)}%
                    </span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
                Top Losers
              </h2>
              <ul className="space-y-2">
                {market.top_losers.slice(0, 3).map((l) => (
                  <li key={l.ticker} className="flex items-center justify-between">
                    <Link
                      to={`/company/${l.ticker}`}
                      className="text-sm font-medium text-slate-200 hover:text-sky-400"
                    >
                      {l.ticker}
                    </Link>
                    <span className="text-sm font-medium text-red-400">
                      {l.change_pct.toFixed(2)}%
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        )}

        {!isLoading && !isError && !market && (
          <Card>
            <p className="text-slate-400">
              No market data yet. Pipeline runs daily at 18:00 EAT.
            </p>
          </Card>
        )}

        <p className="text-center text-sm">
          <Link to="/companies" className="text-sky-400 hover:underline">
            View all companies →
          </Link>
        </p>
      </div>
    </PageShell>
  );
};
```

- [ ] **Step 2: Verify TypeScript compiles**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 3: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/pages/Home.tsx
git commit -m "feat: implement Home page with market overview data"
```

---

## Task 10: Companies page

**Files:**
- Modify: `frontend/src/pages/Companies.tsx` (replace placeholder)
- Create: `frontend/src/pages/Companies.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/Companies.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Companies } from "./Companies";
import * as useCompaniesModule from "../hooks/useCompanies";
import type { CompanyDoc } from "../types";

vi.mock("../hooks/useCompanies");
vi.mock("../lib/auth", () => ({ initAuthListener: vi.fn(() => vi.fn()), logout: vi.fn() }));
vi.mock("../store/useAuthStore", () => ({
  useAuthStore: vi.fn(() => ({ user: null, loading: false })),
}));

const mockCompanies: CompanyDoc[] = [
  {
    id: "SCOM_NR",
    ticker: "SCOM.NR",
    name: "Safaricom PLC",
    short: "SCOM",
    sector: "Telecom",
    color: "#38bdf8",
    icon: "📱",
    csv: "SCOM_NR_raw.csv",
    current_price: 33.05,
    change_pct_today: 1.2,
    signal: "BUY",
    price_preview: [],
    last_updated: "2026-07-15",
  },
  {
    id: "EQTY_NR",
    ticker: "EQTY.NR",
    name: "Equity Group Holdings",
    short: "EQTY",
    sector: "Banking",
    color: "#a78bfa",
    icon: "🏦",
    csv: "EQTY_NR_raw.csv",
    current_price: 55.0,
    change_pct_today: -0.5,
    signal: "HOLD",
    price_preview: [],
    last_updated: "2026-07-15",
  },
];

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Companies page", () => {
  it("renders all companies when data loads", () => {
    vi.mocked(useCompaniesModule.useCompanies).mockReturnValue({
      data: mockCompanies,
      isLoading: false,
      isError: false,
    } as any);

    render(<Companies />, { wrapper: Wrapper });
    expect(screen.getByText("Safaricom PLC")).toBeInTheDocument();
    expect(screen.getByText("Equity Group Holdings")).toBeInTheDocument();
  });

  it("filters companies by search text", async () => {
    vi.mocked(useCompaniesModule.useCompanies).mockReturnValue({
      data: mockCompanies,
      isLoading: false,
      isError: false,
    } as any);

    const user = userEvent.setup();
    render(<Companies />, { wrapper: Wrapper });

    const input = screen.getByPlaceholderText("Search companies...");
    await user.type(input, "safar");

    expect(screen.getByText("Safaricom PLC")).toBeInTheDocument();
    expect(screen.queryByText("Equity Group Holdings")).not.toBeInTheDocument();
  });

  it("shows spinner while loading", () => {
    vi.mocked(useCompaniesModule.useCompanies).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as any);

    render(<Companies />, { wrapper: Wrapper });
    expect(screen.queryByText("Safaricom PLC")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test — expect ImportError**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx vitest run src/pages/Companies.test.tsx
```

Expected: test fails because `Companies` is a placeholder.

- [ ] **Step 3: Replace `frontend/src/pages/Companies.tsx` with full implementation**

```typescript
import type { FC } from "react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { SignalBadge } from "../components/ui/Badge";
import { useCompanies } from "../hooks/useCompanies";
import type { CompanyDoc } from "../types";

const SECTORS = [
  "All", "Banking", "Insurance", "Manufacturing", "Energy", "Telecom",
  "Agricultural", "Construction", "Commercial", "Investment", "REIT",
  "Beverages", "Automobiles", "Tourism", "Transport",
];
const SIGNALS = ["All", "BUY", "HOLD", "SELL"] as const;
type SignalFilter = (typeof SIGNALS)[number];

export const Companies: FC = () => {
  const { data: companies, isLoading, isError } = useCompanies();
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("All");
  const [signal, setSignal] = useState<SignalFilter>("All");

  const filtered = useMemo(() => {
    if (!companies) return [];
    return companies.filter((c) => {
      const q = search.toLowerCase();
      const matchSearch =
        c.name.toLowerCase().includes(q) ||
        c.short.toLowerCase().includes(q) ||
        c.ticker.toLowerCase().includes(q);
      const matchSector = sector === "All" || c.sector === sector;
      const matchSignal = signal === "All" || c.signal === signal;
      return matchSearch && matchSector && matchSignal;
    });
  }, [companies, search, sector, signal]);

  return (
    <PageShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-slate-100">NSE Companies</h1>
          <p className="mt-1 text-slate-400">
            {companies?.length ?? 0} companies tracked
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <input
            type="text"
            placeholder="Search companies..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
          />
          <select
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            {SECTORS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            value={signal}
            onChange={(e) => setSignal(e.target.value as SignalFilter)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            {SIGNALS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        {isLoading && (
          <div className="flex justify-center py-16">
            <Spinner size="lg" />
          </div>
        )}

        {isError && (
          <Card className="border-red-800 bg-red-950/20">
            <p className="text-red-400">Failed to load companies.</p>
          </Card>
        )}

        {!isLoading && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((company) => (
              <CompanyCard key={company.id} company={company} />
            ))}
            {filtered.length === 0 && !isLoading && (
              <p className="col-span-3 py-8 text-center text-slate-500">
                No companies match your filters.
              </p>
            )}
          </div>
        )}
      </div>
    </PageShell>
  );
};

const CompanyCard: FC<{ company: CompanyDoc }> = ({ company }) => {
  const change = company.change_pct_today;
  return (
    <Link to={`/company/${company.id}`}>
      <Card className="h-full cursor-pointer transition-colors hover:border-slate-500">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl">{company.icon}</span>
              <span className="font-semibold text-slate-100">{company.short}</span>
            </div>
            <p className="mt-0.5 text-xs text-slate-500">{company.sector}</p>
          </div>
          {company.signal && <SignalBadge signal={company.signal} />}
        </div>
        <div className="mt-3 flex items-end justify-between">
          <div>
            <p className="text-sm text-slate-400">{company.name}</p>
            {company.current_price !== null && (
              <p className="text-lg font-bold text-slate-100">
                KES {company.current_price.toFixed(2)}
              </p>
            )}
          </div>
          {change !== null && (
            <span
              className={`text-sm font-medium ${
                change >= 0 ? "text-emerald-400" : "text-red-400"
              }`}
            >
              {change >= 0 ? "+" : ""}
              {change.toFixed(2)}%
            </span>
          )}
        </div>
      </Card>
    </Link>
  );
};
```

- [ ] **Step 4: Run Companies tests — expect 3 PASS**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx vitest run src/pages/Companies.test.tsx
```

Expected: `3 passed`

- [ ] **Step 5: Run full test suite — expect 9 PASS**

```powershell
npx vitest run
```

Expected: `9 passed` (3 Badge + 3 AuthGuard + 3 Companies)

- [ ] **Step 6: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/pages/Companies.tsx frontend/src/pages/Companies.test.tsx
git commit -m "feat: implement Companies page with search and sector/signal filters"
```

---

## Task 11: Login + Register pages

**Files:**
- Modify: `frontend/src/pages/Login.tsx` (replace placeholder)
- Modify: `frontend/src/pages/Register.tsx` (replace placeholder)

No unit tests for these pages — they depend on Firebase Auth which requires a live connection. Manual testing via dev server is sufficient.

- [ ] **Step 1: Replace `frontend/src/pages/Login.tsx` with full implementation**

```typescript
import type { FC, FormEvent } from "react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { loginWithEmail, loginWithGoogle } from "../lib/auth";

export const Login: FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleEmailLogin(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await loginWithEmail(email, password);
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleLogin() {
    setError(null);
    setLoading(true);
    try {
      await loginWithGoogle();
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageShell>
      <div className="mx-auto max-w-sm">
        <Card>
          <h1 className="mb-6 text-2xl font-bold text-slate-100">Sign in</h1>

          {error && (
            <p className="mb-4 rounded-lg bg-red-950/50 p-3 text-sm text-red-400">
              {error}
            </p>
          )}

          <form onSubmit={handleEmailLogin} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-slate-400">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-400">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <div className="my-4 flex items-center gap-3">
            <div className="flex-1 border-t border-slate-700" />
            <span className="text-xs text-slate-500">or</span>
            <div className="flex-1 border-t border-slate-700" />
          </div>

          <Button
            variant="secondary"
            className="w-full"
            onClick={handleGoogleLogin}
            disabled={loading}
          >
            Continue with Google
          </Button>

          <p className="mt-4 text-center text-sm text-slate-500">
            No account?{" "}
            <Link to="/register" className="text-sky-400 hover:underline">
              Sign up free
            </Link>
          </p>
        </Card>
      </div>
    </PageShell>
  );
};
```

- [ ] **Step 2: Replace `frontend/src/pages/Register.tsx` with full implementation**

```typescript
import type { FC, FormEvent } from "react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { registerWithEmail, loginWithGoogle } from "../lib/auth";

export const Register: FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleRegister(e: FormEvent) {
    e.preventDefault();
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await registerWithEmail(email, password);
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleRegister() {
    setError(null);
    setLoading(true);
    try {
      await loginWithGoogle();
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Sign up failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageShell>
      <div className="mx-auto max-w-sm">
        <Card>
          <h1 className="mb-2 text-2xl font-bold text-slate-100">Create account</h1>
          <p className="mb-6 text-sm text-slate-400">
            Free forever — unlocks full AI analysis, predictions, and technical indicators.
          </p>

          {error && (
            <p className="mb-4 rounded-lg bg-red-950/50 p-3 text-sm text-red-400">{error}</p>
          )}

          <form onSubmit={handleRegister} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-slate-400">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-400">Password</label>
              <input
                type="password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Creating account…" : "Create account"}
            </Button>
          </form>

          <div className="my-4 flex items-center gap-3">
            <div className="flex-1 border-t border-slate-700" />
            <span className="text-xs text-slate-500">or</span>
            <div className="flex-1 border-t border-slate-700" />
          </div>

          <Button
            variant="secondary"
            className="w-full"
            onClick={handleGoogleRegister}
            disabled={loading}
          >
            Continue with Google
          </Button>

          <p className="mt-4 text-center text-sm text-slate-500">
            Already have an account?{" "}
            <Link to="/login" className="text-sky-400 hover:underline">
              Sign in
            </Link>
          </p>
        </Card>
      </div>
    </PageShell>
  );
};
```

- [ ] **Step 3: Verify TypeScript compiles**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 4: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/pages/Login.tsx frontend/src/pages/Register.tsx
git commit -m "feat: implement Login and Register pages with email + Google Auth"
```

---

## Task 12: Company deep dive page

**Files:**
- Modify: `frontend/src/pages/CompanyDeepDive.tsx` (replace placeholder)

- [ ] **Step 1: Replace `frontend/src/pages/CompanyDeepDive.tsx` with full implementation**

```typescript
import type { FC } from "react";
import { useParams, Link } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { AuthGuard } from "../components/layout/AuthGuard";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { SignalBadge } from "../components/ui/Badge";
import { SignInPrompt } from "../components/company/SignInPrompt";
import { SparkLine } from "../components/charts/SparkLine";
import { PredictionChart } from "../components/charts/PredictionChart";
import { useCompany, useLatestSnapshot, useLatestTechnicals } from "../hooks/useCompany";
import type { SnapshotDoc, TechnicalsDoc } from "../types";

export const CompanyDeepDive: FC = () => {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const { data: company, isLoading, isError } = useCompany(ticker);

  if (isLoading) {
    return (
      <PageShell>
        <div className="flex justify-center py-16">
          <Spinner size="lg" />
        </div>
      </PageShell>
    );
  }

  if (isError || !company) {
    return (
      <PageShell>
        <Card className="border-red-800">
          <p className="text-red-400">Company not found.</p>
          <Link to="/companies" className="mt-2 block text-sm text-sky-400 hover:underline">
            ← Back to companies
          </Link>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <div className="space-y-6">
        {/* Public header */}
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-3xl">{company.icon}</span>
              <h1 className="text-3xl font-bold text-slate-100">{company.name}</h1>
              {company.signal && <SignalBadge signal={company.signal} size="lg" />}
            </div>
            <p className="mt-1 text-slate-400">
              {company.sector} · {company.ticker}
            </p>
          </div>
          <div className="text-right">
            {company.current_price !== null && (
              <>
                <p className="text-3xl font-bold text-slate-100">
                  KES {company.current_price.toFixed(2)}
                </p>
                {company.change_pct_today !== null && (
                  <p
                    className={`text-sm font-medium ${
                      company.change_pct_today >= 0 ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {company.change_pct_today >= 0 ? "+" : ""}
                    {company.change_pct_today.toFixed(2)}% today
                  </p>
                )}
              </>
            )}
          </div>
        </div>

        {/* Public: 30-day price preview */}
        {company.price_preview.length > 0 && (
          <Card>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
              30-Day Price Preview
            </h2>
            <SparkLine data={company.price_preview} color={company.color} />
          </Card>
        )}

        {/* Gated: full analysis */}
        <AuthGuard fallback={<SignInPrompt />}>
          <GatedContent ticker={ticker} />
        </AuthGuard>
      </div>
    </PageShell>
  );
};

const GatedContent: FC<{ ticker: string }> = ({ ticker }) => {
  const { data: snapshot, isLoading: snapLoading } = useLatestSnapshot(ticker);
  const { data: technicals, isLoading: techLoading } = useLatestTechnicals(ticker);

  if (snapLoading || techLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {snapshot ? (
        <SnapshotSection snapshot={snapshot} />
      ) : (
        <Card>
          <p className="text-slate-400">
            No prediction data yet. Pipeline runs daily at 18:00 EAT.
          </p>
        </Card>
      )}

      {snapshot && snapshot.actuals.length > 0 && (
        <Card>
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Actual vs Predicted
          </h2>
          <PredictionChart
            actuals={snapshot.actuals}
            preds={snapshot.preds}
            forecast={snapshot.forecast}
          />
        </Card>
      )}

      {technicals && <TechnicalsSection technicals={technicals} />}
    </div>
  );
};

const SnapshotSection: FC<{ snapshot: SnapshotDoc }> = ({ snapshot }) => (
  <Card>
    <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
      AI Signal
    </h2>
    <div className="flex flex-wrap gap-6">
      <Metric label="Signal" value={<SignalBadge signal={snapshot.signal} size="lg" />} />
      <Metric
        label="Risk-Adjusted"
        value={<SignalBadge signal={snapshot.risk_adjusted_signal} size="lg" />}
      />
      <Metric
        label="Predicted Price"
        value={
          <span className="text-xl font-bold text-slate-100">
            KES {snapshot.predicted_price_KES.toFixed(2)}
          </span>
        }
      />
      <Metric
        label="Expected Move"
        value={
          <span
            className={`text-xl font-bold ${
              snapshot.predicted_change_pct >= 0 ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {snapshot.predicted_change_pct >= 0 ? "+" : ""}
            {snapshot.predicted_change_pct.toFixed(2)}%
          </span>
        }
      />
    </div>
    <p className="mt-4 text-sm text-slate-400">{snapshot.rationale}</p>
    <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <MetricChip label="MAPE" value={`${snapshot.metrics.mape.toFixed(1)}%`} />
      <MetricChip label="RMSE" value={snapshot.metrics.rmse.toFixed(3)} />
      <MetricChip label="MAE" value={snapshot.metrics.mae.toFixed(3)} />
      <MetricChip
        label="Directional Acc."
        value={`${snapshot.metrics.directional_accuracy.toFixed(0)}%`}
      />
    </div>
    <p className="mt-2 text-xs text-slate-600">VaR (95%): {snapshot.var_95_pct.toFixed(2)}%</p>
  </Card>
);

const TechnicalsSection: FC<{ technicals: TechnicalsDoc }> = ({ technicals }) => {
  const fmt = (v: number | null, suffix = "") =>
    v !== null ? `${v.toFixed(2)}${suffix}` : "N/A";

  return (
    <Card>
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
        Technical Indicators
      </h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <MetricChip label="RSI (14)" value={fmt(technicals.rsi_14)} />
        <MetricChip label="SMA 20" value={technicals.sma_20 !== null ? `KES ${fmt(technicals.sma_20)}` : "N/A"} />
        <MetricChip label="SMA 50" value={technicals.sma_50 !== null ? `KES ${fmt(technicals.sma_50)}` : "N/A"} />
        <MetricChip label="SMA 200" value={technicals.sma_200 !== null ? `KES ${fmt(technicals.sma_200)}` : "N/A"} />
        <MetricChip label="EMA 12" value={technicals.ema_12 !== null ? `KES ${fmt(technicals.ema_12)}` : "N/A"} />
        <MetricChip label="EMA 26" value={technicals.ema_26 !== null ? `KES ${fmt(technicals.ema_26)}` : "N/A"} />
        <MetricChip label="Daily Return" value={fmt(technicals.daily_return, "%")} />
        <MetricChip label="Volatility 30d" value={fmt(technicals.volatility_30d, "%")} />
        <MetricChip label="Volume" value={technicals.volume.toLocaleString()} />
        <MetricChip label="Avg Vol 30d" value={technicals.avg_volume_30d.toLocaleString()} />
        {technicals.macd !== null && (
          <MetricChip label="MACD" value={fmt(technicals.macd)} />
        )}
        {technicals.rsi_14 !== null && (
          <MetricChip
            label="RSI Status"
            value={
              technicals.rsi_14 > 70
                ? "Overbought"
                : technicals.rsi_14 < 30
                ? "Oversold"
                : "Neutral"
            }
          />
        )}
      </div>

      {Object.keys(technicals.monthly_heatmap).length > 0 && (
        <div className="mt-6">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Monthly Returns
          </h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(technicals.monthly_heatmap)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([month, ret]) => (
                <div
                  key={month}
                  className={`rounded px-2 py-1 text-xs font-medium ${
                    ret >= 0
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-red-500/20 text-red-400"
                  }`}
                >
                  {month}: {ret >= 0 ? "+" : ""}{ret.toFixed(1)}%
                </div>
              ))}
          </div>
        </div>
      )}
    </Card>
  );
};

const Metric: FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div>
    <p className="text-xs text-slate-500">{label}</p>
    <div className="mt-1">{value}</div>
  </div>
);

const MetricChip: FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-lg bg-slate-900 p-3">
    <p className="text-xs text-slate-500">{label}</p>
    <p className="mt-0.5 text-sm font-semibold text-slate-200">{value}</p>
  </div>
);
```

- [ ] **Step 2: Verify TypeScript compiles**

```powershell
cd "C:\Users\moeng\nse_predictor\frontend"
npx tsc --noEmit 2>&1
```

Expected: no errors.

- [ ] **Step 3: Run full test suite — expect 9 PASS**

```powershell
npx vitest run
```

Expected: `9 passed`

- [ ] **Step 4: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add frontend/src/pages/CompanyDeepDive.tsx
git commit -m "feat: implement Company deep dive page with public header and gated analysis"
```

---

## Task 13: Update deploy.yml for Cloudflare Pages

**Files:**
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Replace `.github/workflows/deploy.yml` with full Wrangler deploy**

```yaml
name: Deploy Frontend

on:
  push:
    branches: [main]
    paths:
      - "frontend/**"

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci
        working-directory: frontend

      - name: Build
        env:
          VITE_FIREBASE_API_KEY: ${{ secrets.VITE_FIREBASE_API_KEY }}
          VITE_FIREBASE_AUTH_DOMAIN: ${{ secrets.VITE_FIREBASE_AUTH_DOMAIN }}
          VITE_FIREBASE_PROJECT_ID: ${{ secrets.VITE_FIREBASE_PROJECT_ID }}
          VITE_FIREBASE_STORAGE_BUCKET: ${{ secrets.VITE_FIREBASE_STORAGE_BUCKET }}
          VITE_FIREBASE_MESSAGING_SENDER_ID: ${{ secrets.VITE_FIREBASE_MESSAGING_SENDER_ID }}
          VITE_FIREBASE_APP_ID: ${{ secrets.VITE_FIREBASE_APP_ID }}
        run: npm run build
        working-directory: frontend

      - name: Deploy to Cloudflare Pages
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy dist --project-name=nse-intelligence --branch=main
          workingDirectory: frontend
```

- [ ] **Step 2: Verify `frontend/package-lock.json` will exist after Task 1**

The `npm install` in Task 1 creates `package-lock.json`. Confirm:

```powershell
Test-Path "C:\Users\moeng\nse_predictor\frontend\package-lock.json"
```

Expected: `True`

- [ ] **Step 3: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add .github/workflows/deploy.yml
git commit -m "feat: wire Cloudflare Pages deploy via Wrangler in deploy.yml"
```

---

## Setup required before first deploy

Before the Cloudflare Pages deploy workflow can run, do these once in GitHub and Cloudflare:

1. **Create Cloudflare Pages project** named `nse-intelligence` in your Cloudflare dashboard (Pages → Create project → Connect Git or create directly).

2. **Add GitHub Secrets** (Settings → Secrets → Actions):
   - `VITE_FIREBASE_API_KEY`
   - `VITE_FIREBASE_AUTH_DOMAIN`
   - `VITE_FIREBASE_PROJECT_ID`
   - `VITE_FIREBASE_STORAGE_BUCKET`
   - `VITE_FIREBASE_MESSAGING_SENDER_ID`
   - `VITE_FIREBASE_APP_ID`
   - `CLOUDFLARE_API_TOKEN` — from Cloudflare → My Profile → API Tokens → Create Token (use "Edit Cloudflare Workers" template)
   - `CLOUDFLARE_ACCOUNT_ID` — from Cloudflare dashboard URL

3. **Create `frontend/.env.local`** (gitignored) with real Firebase values for local dev:

```
VITE_FIREBASE_API_KEY=your_key_here
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project-id
VITE_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
VITE_FIREBASE_APP_ID=your_app_id
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| React 18 + TypeScript + Vite | Task 1 |
| Tailwind CSS dark theme | Task 1 |
| Firebase JS SDK v10 | Task 2 |
| TypeScript types for all Firestore docs | Task 2 |
| Zustand auth store | Task 3 |
| Google + email/password auth | Task 3, 11 |
| Firestore query helpers | Task 4 |
| TanStack Query hooks | Task 4 |
| SignalBadge, Card, Spinner, Button | Task 5 |
| SparkLine chart | Task 6 |
| Actual vs Predicted + Forecast chart | Task 6 |
| Navbar with auth-aware links | Task 7 |
| PageShell layout | Task 7 |
| AuthGuard with blur overlay | Task 7 |
| SignInPrompt CTA | Task 7 |
| React Router v6 routes | Task 8 |
| Home page: market overview, gainers/losers, signal distribution | Task 9 |
| Companies page: search, sector filter, signal filter | Task 10 |
| Login + Register pages | Task 11 |
| Company deep dive: public header, price preview | Task 12 |
| Company deep dive: gated AI signal, prediction chart, technicals | Task 12 |
| Monthly performance heatmap | Task 12 |
| Cloudflare Pages deploy via Wrangler | Task 13 |
| VITE_FIREBASE_* env vars in CI | Task 13 |

**No placeholders found.**

**Type consistency:** `CompanyDoc.id` (string, safe ticker) used consistently in `fetchAllCompanies`, `CompanyCard` link, `useCompany` parameter. `MarketOverviewDoc` field names match Firestore writer in Plan 1 (`top_gainers`, `top_losers`, `signal_distribution`). `SnapshotDoc` fields match Plan 1 `build_company_result` output.
