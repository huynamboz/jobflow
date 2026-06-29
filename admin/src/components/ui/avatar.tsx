import { cn } from "@/lib/utils";

/**
 * JobFlow Avatar — round image avatar with an initials fallback. Falls back
 * to a tinted blue circle with the first letter when `src` is missing.
 * `ring` adds the white photo ring used over cover images.
 */
export interface AvatarProps {
  src?: string | null;
  name?: string;
  size?: number;
  ring?: boolean;
  className?: string;
}

function initials(name?: string) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function Avatar({ src, name, size = 40, ring = false, className }: AvatarProps) {
  const ringStyle = ring
    ? { border: "3px solid #fff", boxShadow: "0 2px 10px rgba(0,0,0,.1)" }
    : undefined;
  if (src) {
    return (
      <div
        role="img"
        aria-label={name}
        className={cn("shrink-0 rounded-full bg-jn-sunken bg-cover bg-center", className)}
        style={{ width: size, height: size, backgroundImage: `url('${src}')`, ...ringStyle }}
      />
    );
  }
  return (
    <div
      aria-label={name}
      className={cn(
        "grid shrink-0 place-items-center rounded-full bg-jn-primary-soft font-bold text-jn-primary",
        className,
      )}
      style={{ width: size, height: size, fontSize: size * 0.38, ...ringStyle }}
    >
      {initials(name)}
    </div>
  );
}

/**
 * Overlapping avatar stack with an optional "+N" overflow chip — the
 * collaborators cluster from the candidate header.
 */
export interface AvatarStackProps {
  people: { src?: string | null; name?: string }[];
  max?: number;
  size?: number;
  className?: string;
}

export function AvatarStack({ people, max = 3, size = 26, className }: AvatarStackProps) {
  const shown = people.slice(0, max);
  const overflow = people.length - shown.length;
  return (
    <div className={cn("flex items-center", className)}>
      {shown.map((p, i) => (
        <div key={i} style={{ marginLeft: i === 0 ? 0 : -9, border: "2px solid #fff", borderRadius: "9999px" }}>
          <Avatar src={p.src} name={p.name} size={size} />
        </div>
      ))}
      {overflow > 0 && (
        <span
          className="grid place-items-center rounded-full bg-jn-ink font-bold text-white"
          style={{ width: size, height: size, marginLeft: -9, border: "2px solid #fff", fontSize: size * 0.38 }}
        >
          +{overflow}
        </span>
      )}
    </div>
  );
}

export default Avatar;
