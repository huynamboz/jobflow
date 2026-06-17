import { NavLink, useLocation } from "react-router-dom";
import { useState } from "react";
import {
  IconChevronDown,
  IconChevronsLeft,
  IconChevronsRight,
  IconLogout,
  IconPlugConnected,
  IconSettings,
} from "@tabler/icons-react";

import { useAuthStore } from "@/stores/auth.store";
import { adminConfig } from "@/config/admin";

const SIDEBAR_WIDTH = 272;
const SIDEBAR_WIDTH_MINI = 76;

// Dark sidebar palette — sits against the soft-grey app body.
// Anchored on NODE --c8/--c9 inks; tinted whites for foreground tiers.
// Howard-style admin sidebar — deep navy surface with a cyan accent.
const T = {
  bg:        "#0f1b3f",                    // deep navy (howard sidebar)
  surface:   "#16244d",                    // slightly lifted
  surface2:  "rgba(255,255,255,0.06)",     // hover surface on dark
  line:      "rgba(255,255,255,0.08)",     // subtle separator
  ink:       "#ffffff",                    // active text / strongest
  ink2:      "#cbd5e1",                    // slate-300 — default nav text
  ink3:      "#94a3b8",                    // slate-400 — icon / close button
  ink4:      "#64748b",                    // slate-500 — section caps / very muted
  accent:    "#22d3ee",                    // cyan-400
  accent600: "#06b6d4",                    // cyan-500
  accent50:  "rgba(34,211,238,0.14)",      // accent tint for active state
};


export interface AdminSidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
  /** Desktop-only icon-rail mode; the mobile drawer always renders full width. */
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function AdminSidebar({
  isOpen = true,
  onClose,
  isCollapsed = false,
  onToggleCollapse,
}: AdminSidebarProps) {
  const location = useLocation();
  const logout = useAuthStore((state) => state.logout);
  // System (all technical tooling) starts collapsed so the staffing workflow leads.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({ System: true });
  // When the mobile drawer is open, isOpen wins — the rail only applies on desktop.
  const mini = isCollapsed && !isOpen;

  const toggleSection = (title: string) =>
    setCollapsed((prev) => ({ ...prev, [title]: !prev[title] }));

  const isActive = (href: string) =>
    href === "/admin" ? location.pathname === "/admin" : location.pathname.startsWith(href);

  return (
    <>
      {isOpen && (
        <button
          aria-label="Close sidebar"
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          type="button"
          onClick={onClose}
        />
      )}

      <aside
        style={{
          width: mini ? SIDEBAR_WIDTH_MINI : SIDEBAR_WIDTH,
          background: T.bg,
          borderRight: `1px solid ${T.line}`,
          display: "flex",
          flexDirection: "column",
          padding: mini ? "20px 12px 24px" : "20px 16px 24px",
          gap: 18,
          position: "fixed",
          left: 0,
          top: 0,
          height: "100vh",
          zIndex: 50,
          transition: "transform 0.2s ease-out, width 0.2s ease-out, padding 0.2s ease-out",
        }}
        className={isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
      >
        {/* Brand */}
        <div
          style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: mini ? "6px 0 10px" : "6px 8px 10px",
            justifyContent: mini ? "center" : undefined,
            fontWeight: 800, letterSpacing: "-0.02em", fontSize: 17,
          }}
        >
          <NavLink
            title={mini ? "jobflow" : undefined}
            to="/admin"
            style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none", color: T.ink }}
          >
            <div style={{
              width: 30, height: 30, borderRadius: 10,
              background: "#1a1a1a", color: "#fff",
              display: "grid", placeItems: "center",
              fontWeight: 800, fontSize: 14,
              position: "relative", overflow: "hidden",
            }}>
              <span style={{
                position: "absolute", inset: 0,
                background: `radial-gradient(circle at 70% 30%, ${T.accent}, transparent 60%)`,
                opacity: 0.9,
              }} />
              <span style={{ position: "relative", zIndex: 1 }}>J</span>
            </div>
            {!mini && (
              <div style={{ display: "flex", flexDirection: "column", lineHeight: 1 }}>
                <span style={{ color: T.ink }}>jobflow</span>
                <span style={{ fontSize: 10.5, fontWeight: 500, color: T.ink4, marginTop: 3, letterSpacing: "0.01em" }}>HR data platform</span>
              </div>
            )}
          </NavLink>

          {!mini && (
            <button
              aria-label="Collapse sidebar"
              className="hidden lg:flex"
              title="Collapse sidebar"
              type="button"
              onClick={onToggleCollapse}
              style={{
                marginLeft: "auto", background: "transparent", border: "none",
                cursor: "pointer", color: T.ink3, alignItems: "center",
                padding: 4, borderRadius: 8,
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = T.surface2; e.currentTarget.style.color = T.ink; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = T.ink3; }}
            >
              <IconChevronsLeft size={18} />
            </button>
          )}
        </div>

        {mini && (
          <button
            aria-label="Expand sidebar"
            className="hidden lg:flex"
            title="Expand sidebar"
            type="button"
            onClick={onToggleCollapse}
            style={{
              alignItems: "center", justifyContent: "center",
              padding: "8px 0", borderRadius: 12, width: "100%",
              background: "transparent", border: "none",
              cursor: "pointer", color: T.ink3, marginTop: -10,
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = T.surface2; e.currentTarget.style.color = T.ink; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = T.ink3; }}
          >
            <IconChevronsRight size={18} />
          </button>
        )}

        {/* Nav */}
        <div style={{ flex: 1, overflow: "auto", marginRight: -6, paddingRight: 6, display: "flex", flexDirection: "column", gap: 10 }}>
          {adminConfig.navSections.map((section, sectionIndex) => {
            const open = !collapsed[section.title];
            // In the icon rail there is no section header to re-expand from,
            // so always show every item and separate sections with a divider.
            const showItems = mini || open;
            return (
              <div key={section.title} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {mini ? (
                  sectionIndex > 0 && (
                    <div style={{ height: 1, background: T.line, margin: "4px 8px 8px" }} />
                  )
                ) : (
                  <button
                    type="button"
                    onClick={() => toggleSection(section.title)}
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "6px 10px 4px",
                      fontSize: 10.5, fontWeight: 700, color: T.ink4,
                      textTransform: "uppercase", letterSpacing: "0.1em",
                      background: "transparent", border: "none", cursor: "pointer",
                      textAlign: "left", width: "100%",
                    }}
                  >
                    {section.title}
                    <IconChevronDown
                      size={20}
                      style={{
                        marginLeft: "auto",
                        transform: open ? "rotate(0deg)" : "rotate(-90deg)",
                        transition: "transform 0.15s",
                        color: T.ink4,
                      }}
                    />
                  </button>
                )}

                {showItems && section.items.map((item) => {
                  const active = isActive(item.href);
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.href}
                      title={mini ? item.label : undefined}
                      to={item.href}
                      onClick={() => onClose?.()}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        justifyContent: mini ? "center" : undefined,
                        padding: mini ? "10px 0" : "8px 10px", borderRadius: 12,
                        color: active ? T.ink : T.ink2,
                        background: active ? "rgba(255,255,255,0.10)" : "transparent",
                        fontWeight: active ? 600 : 500, fontSize: 13.5,
                        textDecoration: "none",
                        transition: "background 0.14s, color 0.14s",
                      }}
                      onMouseEnter={(e) => {
                        if (!active) {
                          e.currentTarget.style.background = "rgba(255,255,255,0.06)";
                          e.currentTarget.style.color = T.ink;
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!active) {
                          e.currentTarget.style.background = "transparent";
                          e.currentTarget.style.color = T.ink2;
                        }
                      }}
                    >
                      <Icon
                        size={mini ? 18 : 16}
                        style={{ color: active ? T.ink2 : T.ink4, flexShrink: 0 }}
                      />
                      {!mini && <span>{item.label}</span>}
                    </NavLink>
                  );
                })}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ borderTop: `1px solid ${T.line}`, paddingTop: 10, display: "flex", flexDirection: "column", gap: 2 }}>
          <NavLink
            title={mini ? "Integrations" : undefined}
            to="/admin/integrations"
            onClick={() => onClose?.()}
            style={{
              display: "flex", alignItems: "center", gap: 10,
              justifyContent: mini ? "center" : undefined,
              padding: mini ? "10px 0" : "8px 10px", borderRadius: 12,
              color: T.ink2, fontWeight: 500, fontSize: 13.5, textDecoration: "none",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = T.surface2; e.currentTarget.style.color = T.ink; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = T.ink2; }}
          >
            <IconPlugConnected size={mini ? 18 : 16} style={{ flexShrink: 0 }} />
            {!mini && "Integrations"}
          </NavLink>

          <NavLink
            title={mini ? "Settings" : undefined}
            to="/admin/settings"
            onClick={() => onClose?.()}
            style={{
              display: "flex", alignItems: "center", gap: 10,
              justifyContent: mini ? "center" : undefined,
              padding: mini ? "10px 0" : "8px 10px", borderRadius: 12,
              color: T.ink2, fontWeight: 500, fontSize: 13.5, textDecoration: "none",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = T.surface2; e.currentTarget.style.color = T.ink; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = T.ink2; }}
          >
            <IconSettings size={mini ? 18 : 16} style={{ flexShrink: 0 }} />
            {!mini && "Settings"}
          </NavLink>

          <button
            title={mini ? "Logout" : undefined}
            type="button"
            onClick={logout}
            style={{
              display: "flex", alignItems: "center", gap: 10,
              justifyContent: mini ? "center" : undefined,
              padding: mini ? "10px 0" : "8px 10px", borderRadius: 12,
              background: "transparent", border: "none",
              color: T.ink2, fontWeight: 500, fontSize: 13.5,
              cursor: "pointer", textAlign: "left", width: "100%",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = T.surface2; e.currentTarget.style.color = T.ink; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = T.ink2; }}
          >
            <IconLogout size={mini ? 18 : 16} style={{ flexShrink: 0 }} />
            {!mini && "Logout"}
          </button>
        </div>
      </aside>
    </>
  );
}
