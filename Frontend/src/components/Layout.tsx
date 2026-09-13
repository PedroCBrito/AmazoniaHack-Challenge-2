import { NavLink, Outlet } from "react-router-dom";
import type { ReactNode } from "react";

function NavItem({ to, children }: { to: string; children: ReactNode }) {
  return (
    <NavLink
      to={to}
    className={({ isActive }: { isActive: boolean }) =>
        [
          "block px-3 py-2 text-sm border-l-2 transition-colors",
          isActive
            ? "border-forest text-forest font-medium bg-forest/5"
            : "border-transparent text-ink/70 hover:text-ink hover:border-line",
        ].join(" ")
      }
    >
      {children}
    </NavLink>
  );
}

function Layout() {
  return (
    <div className="min-h-screen flex">
      <aside className="w-56 shrink-0 border-r border-line flex flex-col">
        <div className="px-4 py-5 border-b border-line">
          <p className="font-serif text-lg leading-tight text-ink">Extração de<br />Documentos</p>
        </div>
        <nav className="flex-1 py-3">
          <NavItem to="/">Novo documento</NavItem>
          <NavItem to="/documentos">Documentos</NavItem>
        </nav>
        <div className="px-4 py-3 border-t border-line text-xs text-ink/50">Fiscalização ambiental</div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-14 flex items-center px-6 border-b border-line">
          <h1 className="font-serif text-base text-ink">Extração de Documentos Ambientais</h1>
        </header>
        <main className="flex-1 px-6 py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default Layout;
