import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";
import { IconSearch } from "@tabler/icons-react";

import { cn } from "@/lib/utils";

/**
 * JobNest search field — the sunken pill input with a leading magnifier used
 * in the top bar and toolbars. Wraps a native <input>; forwards all props.
 * Constrain width at the call site (e.g. `className="max-w-[420px]"`).
 */
export interface SearchInputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Wrapper className (width, margins). Input styling is fixed. */
  className?: string;
}

export const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(
  function SearchInput({ className, placeholder = "Search…", ...rest }, ref) {
    return (
      <div
        className={cn(
          "flex w-full items-center gap-2.5 rounded-jn-btn bg-jn-sunken px-3.5 py-2.5",
          "focus-within:ring-2 focus-within:ring-jn-primary/30",
          className,
        )}
      >
        <IconSearch size={17} className="shrink-0 text-jn-muted" />
        <input
          ref={ref}
          placeholder={placeholder}
          className="w-full border-none bg-transparent text-[13.5px] text-jn-ink outline-none placeholder:text-jn-muted"
          {...rest}
        />
      </div>
    );
  },
);

export default SearchInput;
