import { useState } from "react";
import { Outlet } from "react-router-dom";

import { AdminHeader } from "@/components/admin/admin-header";
import { AdminSidebar } from "@/components/admin/admin-sidebar";

export default function AdminLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen" style={{ background: "var(--c2)" }}>
      <AdminSidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <div className="flex flex-col min-h-screen transition-[margin] duration-200 lg:ml-[272px]">
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
