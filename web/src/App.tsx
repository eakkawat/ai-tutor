import { useQuery } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import Home from "./pages/Home";
import Library from "./pages/Library";
import Picker from "./pages/Picker";
import ProjectForm from "./pages/ProjectForm";
import Setup from "./pages/Setup";
import Soon from "./pages/Soon";
import SkillMap from "./pages/SkillMap";
import SkillReview from "./pages/SkillReview";
import Session from "./pages/Session";
import Source from "./pages/Source";

const TABS = [
  { to: "/", label: "Home", end: true },
  { to: "/skills", label: "Skill map" },
  { to: "/concepts", label: "Concepts" },
  { to: "/library", label: "Library" },
  { to: "/progress", label: "Progress" },
  { to: "/profile", label: "How I learn" },
];

function Header({ tabs }: { tabs: boolean }) {
  return (
    <header className="header">
      <span className="brand">Tutor</span>
      {tabs && (
        <nav className="tabs" aria-label="Main">
          {TABS.map((t) => <NavLink key={t.to} to={t.to} end={t.end} className="tab">{t.label}</NavLink>)}
        </nav>
      )}
    </header>
  );
}

export default function App() {
  const { pathname } = useLocation();
  // The check runs on every start (A1). Verifying the server is one call to it; offline leaves the app usable.
  const setup = useQuery({ queryKey: ["setup"], queryFn: () => api.setupStatus(true), retry: false });
  const onSetup = pathname === "/setup";

  if (setup.isPending) return <><Header tabs={false} /><main className="page narrow" role="status">Checking this computer…</main></>;
  if (setup.data && !setup.data.can_continue && !onSetup) return <Navigate to="/setup" replace />;

  return (
    <>
      <Header tabs={!onSetup} />
      <Routes>
        <Route path="/setup" element={<Setup />} />
        <Route path="/" element={<Home />} />
        <Route path="/new" element={<Picker />} />
        <Route path="/project/new" element={<ProjectForm />} />
        <Route path="/session/:id" element={<Session />} />
        <Route path="/library" element={<Library />} />
        <Route path="/source/:chunkId" element={<Source />} />
        <Route path="/skills" element={<SkillMap />} />
        <Route path="/skills/review" element={<SkillReview />} />
        <Route path="/concepts" element={<Soon title="Concepts" />} />
        <Route path="/progress" element={<Soon title="Progress" />} />
        <Route path="/profile" element={<Soon title="How I learn" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
