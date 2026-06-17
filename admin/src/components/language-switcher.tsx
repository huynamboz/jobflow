import { useTranslation } from "react-i18next";
import { IconWorld, IconCheck } from "@tabler/icons-react";
import { Popover, PopoverContent, PopoverTrigger } from "@heroui/popover";

import { SUPPORTED_LANGUAGES } from "@/i18n";

// Header palette (mirrors admin-header.tsx warm-neutral surfaces).
const N = {
  c3: "#f1f1f1", line: "#ececec",
  ink: "#121212", inkSoft: "#323232", muted: "#7b7b7b",
};

/**
 * Header language switcher. Renders one option per SUPPORTED_LANGUAGES,
 * highlights the active language, and persists the choice via i18next's
 * localStorage detector on change (no reload).
 */
export function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const active = (i18n.resolvedLanguage || i18n.language || "vi").split("-")[0];

  return (
    <Popover placement="bottom-end">
      <PopoverTrigger>
        <button
          type="button"
          aria-label="Change language"
          className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border-0 bg-transparent px-2 transition-colors"
          style={{ color: N.inkSoft }}
          onMouseEnter={(e) => { e.currentTarget.style.background = N.c3; e.currentTarget.style.color = N.ink; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = N.inkSoft; }}
        >
          <IconWorld size={18} strokeWidth={1.5} />
          <span style={{ fontSize: 12.5, fontWeight: 600, textTransform: "uppercase" }}>{active}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent>
        <div className="w-44 py-1">
          {SUPPORTED_LANGUAGES.map((lang) => {
            const isActive = lang.code === active;
            return (
              <button
                key={lang.code}
                type="button"
                onClick={() => { void i18n.changeLanguage(lang.code); }}
                className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left transition-colors"
                style={{
                  fontSize: 13,
                  fontWeight: isActive ? 600 : 500,
                  color: isActive ? N.ink : N.inkSoft,
                  background: isActive ? N.c3 : "transparent",
                }}
                onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = N.c3; }}
                onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
              >
                <span>{lang.label}</span>
                {isActive
                  ? <IconCheck size={15} style={{ color: N.ink }} />
                  : <span style={{ fontSize: 10, color: N.muted, textTransform: "uppercase" }}>{lang.code}</span>}
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
