import { useEffect, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

type Theme = "system" | "light" | "dark";

function readTheme(): Theme {
  try {
    const saved = localStorage.getItem("theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

export function Layout() {
  const [theme, setTheme] = useState<Theme>(readTheme);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("theme", theme);
    } catch {
      // Storage may be unavailable (private mode); the choice then lasts for this page only.
    }
  }, [theme]);

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="app-header">
        <Link to="/" className="brand">
          LLM Eval
        </Link>
        <nav aria-label="Main">
          <NavLink to="/" end>
            Projects
          </NavLink>
          <a href="/docs" target="_blank" rel="noreferrer">
            API docs
          </a>
        </nav>
        <label className="theme-toggle">
          <span className="sr-only">Theme</span>
          <select value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
            <option value="system">System theme</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
      </header>
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  );
}
