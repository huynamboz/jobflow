import { useState } from "react";
import { Outlet } from "react-router-dom";

import { AdminHeader } from "@/components/admin/admin-header";
import { AdminSidebar } from "@/components/admin/admin-sidebar";

const COLLAPSE_KEY = "admin-sidebar-collapsed";

export default function AdminLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_KEY) === "1",
  );

  const toggleCollapsed = () =>
    setSidebarCollapsed((v) => {
      localStorage.setItem(COLLAPSE_KEY, v ? "0" : "1");
      return !v;
    });

  return (
    <div className="min-h-screen" style={{ background: "var(--c2)" }}>
      <AdminSidebar
        isCollapsed={sidebarCollapsed}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onToggleCollapse={toggleCollapsed}
      />
      <div
        className={`flex flex-col min-h-screen transition-[margin] duration-200 ${
          sidebarCollapsed ? "lg:ml-[76px]" : "lg:ml-[272px]"
        }`}
      >
        <div className="sticky top-0 z-30 shrink-0">
          <AdminHeader onMenuClick={() => setSidebarOpen((v) => !v)} />
        </div>
        <main className="flex-1 p-4 md:p-6">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
