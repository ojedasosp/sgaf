import { useLocation, useNavigate } from "react-router-dom";

const NAV_ITEMS = [
  { label: "Dashboard", path: "/dashboard", icon: "⊞" },
  { label: "Activos", path: "/assets", icon: "◈" },
  { label: "Depreciación", path: "/depreciation", icon: "∿" },
  { label: "Reportes PDF", path: "/reports", icon: "⎘" },
  { label: "Exportar ZEUS", path: "/export", icon: "⊡" },
  { label: "Configuración", path: "/settings", icon: "⊶" },
] as const;

export default function Sidebar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();

  return (
    <aside className="flex h-screen w-[240px] min-w-[240px] flex-col border-r border-[#d5c4a1] bg-[#ebdbb2]">
      {/* Logo */}
      <div className="border-b border-[#d5c4a1] px-5 py-5">
        <p className="text-[15px] font-semibold tracking-tight text-[#3c3836]">
          SGAF
        </p>
        <p className="mt-0.5 text-[10px] text-[#7c6f64]">
          Gestión de Activos Fijos
        </p>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3">
        {NAV_ITEMS.map((item) => {
          const isActive =
            pathname === item.path || pathname.startsWith(item.path + "/");
          return (
            <button
              key={item.path}
              type="button"
              onClick={() => navigate(item.path)}
              className={[
                "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-[13px] transition-colors",
                isActive
                  ? "border-l-[3px] border-[#458588] bg-[#d5c4a1] font-medium text-[#3c3836]"
                  : "border-l-[3px] border-transparent text-[#665c54] hover:bg-[#d5c4a1]",
              ].join(" ")}
            >
              <span className="w-4 text-center text-sm">{item.icon}</span>
              {item.label}
            </button>
          );
        })}
      </nav>

      {/* User section */}
      <div className="border-t border-[#d5c4a1] px-4 py-3.5">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#458588] text-[11px] font-semibold text-white">
            A
          </div>
          <span className="text-[12px] text-[#7c6f64]">Usuario</span>
        </div>
      </div>
    </aside>
  );
}
