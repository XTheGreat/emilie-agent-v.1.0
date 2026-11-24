// Small building blocks on Radix primitives, styled like the Claude app.
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Dialog as D, DropdownMenu as M, Popover as P, Switch as S, ToggleGroup as T, Tooltip as Tt } from "radix-ui";
import { cn } from "@/lib/util";
import { Check, ChevronRight, Loader, X } from "./icons";

// ------------------------------------------------------------------ buttons
type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "subtle";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, BtnProps>(function Button(
  { variant = "secondary", size = "md", loading, className, children, disabled, ...rest }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap transition-colors select-none",
        "disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        size === "sm" && "h-[22px] px-2 text-[11.5px]",
        size === "md" && "h-[24px] px-2.5 text-[11.5px]",
        size === "lg" && "h-8 px-3.5 text-[12.5px]",
        variant === "primary" && "bg-text-000 text-bg-100 hover:opacity-90",
        variant === "secondary" && "bg-active text-text-100 hover:brightness-110",
        variant === "ghost" && "text-text-200 hover:bg-hover hover:text-text-100",
        variant === "subtle" && "bg-bg-300 text-text-100 hover:bg-active",
        variant === "danger" && "bg-danger text-white hover:opacity-90",
        className,
      )}
      {...rest}
    >
      {loading && <Loader className="animate-spin" size={12} />}
      {children}
    </button>
  );
});

export const IconButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean; size?: number }>(
  function IconButton({ active, size = 24, className, children, ...rest }, ref) {
    return (
      <button
        ref={ref}
        style={{ width: size, height: size }}
        className={cn(
          "inline-flex items-center justify-center rounded-[5px] text-text-200 transition-colors hover:bg-hover hover:text-text-000",
          "disabled:opacity-40 disabled:pointer-events-none",
          active && "bg-active text-text-100",
          className,
        )}
        {...rest}
      >
        {children}
      </button>
    );
  },
);

// ------------------------------------------------------------------ tooltip
export function Tip({ content, children, side = "bottom", delay, hidden }: {
  content: ReactNode; children: ReactNode; side?: "top" | "bottom" | "left" | "right"; delay?: number; hidden?: boolean;
}) {
  if (!content) return <>{children}</>;
  return (
    <Tt.Root delayDuration={delay ?? 450} open={hidden ? false : undefined}>
      <Tt.Trigger asChild>{children}</Tt.Trigger>
      <Tt.Portal>
        <Tt.Content side={side} sideOffset={6}
          className="z-[100] max-w-xs rounded-[5px] border border-border-400 bg-menu px-2 py-1 text-[11px] text-text-100 shadow-md animate-pop">
          {content}
        </Tt.Content>
      </Tt.Portal>
    </Tt.Root>
  );
}

/** A tooltip with a title, an optional shortcut on the right and a grey line under it. */
export function TipBody({ title, desc, keys }: { title: ReactNode; desc?: ReactNode; keys?: string }) {
  return (
    <div className="flex max-w-[260px] flex-col gap-[2px] py-[1px]">
      <div className="flex items-baseline gap-3">
        <span className="font-medium text-text-100">{title}</span>
        {keys && <span className="ml-auto shrink-0 text-text-400">{keys}</span>}
      </div>
      {desc && <div className="text-text-300">{desc}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ dropdown menu
export const Menu = M.Root;
export const MenuTrigger = M.Trigger;
export const MenuSub = M.Sub;

export function MenuContent({ children, className, align = "start", side, sideOffset = 6, ...rest }: M.DropdownMenuContentProps) {
  return (
    <M.Portal>
      <M.Content align={align} side={side} sideOffset={sideOffset} collisionPadding={8}
        className={cn("z-[90] min-w-[180px] rounded-[9px] border border-[var(--dropdown-border)] bg-[var(--dropdown-bg)] p-[5px] text-[12px] text-text-100 shadow-menu animate-pop outline-none", className)}
        {...rest}>
        {children}
      </M.Content>
    </M.Portal>
  );
}

export function MenuItem({ icon, children, shortcut, danger, checked, checkClass, className, ...rest }:
  M.DropdownMenuItemProps & { icon?: ReactNode; shortcut?: string; danger?: boolean; checked?: boolean; checkClass?: string }) {
  return (
    <M.Item
      className={cn(
        "flex min-h-[21px] cursor-default items-center gap-[9px] rounded-[5px] px-[7px] py-[3px] leading-[15px] outline-none select-none",
        "data-[highlighted]:bg-active data-[highlighted]:text-text-000 data-[disabled]:opacity-40",
        danger && "text-danger data-[highlighted]:text-danger",
        className,
      )}
      {...rest}
    >
      {icon && <span className="flex w-[15px] shrink-0 justify-center text-text-100 [&>svg]:h-[14px] [&>svg]:w-[14px]">{icon}</span>}
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {shortcut && <span className="text-[10.5px] text-text-500">{shortcut}</span>}
      {checked && <Check size={13} className={checkClass || "text-text-100"} />}
    </M.Item>
  );
}

export function MenuSubTrigger({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <M.SubTrigger className="flex min-h-[21px] cursor-default items-center gap-[9px] rounded-[5px] px-[7px] py-[3px] leading-[15px] outline-none data-[highlighted]:bg-active data-[state=open]:bg-active">
      {icon && <span className="flex w-[15px] shrink-0 justify-center text-text-100 [&>svg]:h-[14px] [&>svg]:w-[14px]">{icon}</span>}
      <span className="flex-1">{children}</span>
      <ChevronRight size={13} className="text-text-400" />
    </M.SubTrigger>
  );
}

export function MenuSubContent({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <M.Portal>
      <M.SubContent sideOffset={6} collisionPadding={8}
        className={cn("z-[95] min-w-[180px] rounded-[9px] border border-[var(--dropdown-border)] bg-[var(--dropdown-bg)] p-[5px] text-[12px] text-text-100 shadow-menu animate-pop", className)}>
        {children}
      </M.SubContent>
    </M.Portal>
  );
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return <M.Label className="truncate px-[7px] pb-[4px] pt-[3px] text-[11px] font-medium text-text-300">{children}</M.Label>;
}

export function MenuSep() {
  return <M.Separator className="mx-[2px] my-[4px] h-px bg-[var(--dropdown-sep)]" />;
}

// ------------------------------------------------------------------ popover
export const Pop = P.Root;
export const PopTrigger = P.Trigger;
export const PopAnchor = P.Anchor;
export function PopContent({ children, className, align = "start", side, sideOffset = 6, ...rest }: P.PopoverContentProps) {
  return (
    <P.Portal>
      <P.Content align={align} side={side} sideOffset={sideOffset} collisionPadding={8}
        className={cn("z-[90] rounded-[9px] border border-[var(--dropdown-border)] bg-[var(--dropdown-bg)] text-[12px] text-text-100 shadow-menu animate-pop outline-none", className)}
        {...rest}>
        {children}
      </P.Content>
    </P.Portal>
  );
}

// ------------------------------------------------------------------ dialog
export function Modal({ open, onOpenChange, title, description, children, className, wide, hideClose }: {
  open: boolean; onOpenChange: (o: boolean) => void; title?: ReactNode; description?: ReactNode; children: ReactNode;
  className?: string; wide?: boolean; hideClose?: boolean;
}) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[80] bg-black/40 animate-fade-in" />
        <D.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-[81] max-h-[85vh] w-[calc(100vw-48px)] -translate-x-1/2 -translate-y-1/2 overflow-hidden",
            "flex flex-col rounded-xl border border-border-300 bg-bg-200 dark:bg-[#303030] text-text-100 shadow-menu outline-none animate-pop",
            wide ? "max-w-[640px]" : "max-w-[420px]",
            className,
          )}
          aria-describedby={undefined}
        >
          {title !== undefined && (
            <div className="flex items-start justify-between gap-4 px-5 pt-4 pb-1">
              <div className="min-w-0">
                <D.Title className="text-[15px] font-semibold text-text-100">{title}</D.Title>
                {description && <D.Description className="mt-1 text-[12px] text-text-400">{description}</D.Description>}
              </div>
              {!hideClose && (
                <D.Close asChild>
                  <IconButton aria-label="Close" className="-mr-2 -mt-1"><X size={15} /></IconButton>
                </D.Close>
              )}
            </div>
          )}
          {title === undefined && <D.Title className="sr-only">Dialog</D.Title>}
          {children}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

// ------------------------------------------------------------------ form controls
export function Switch({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <S.Root checked={checked} onCheckedChange={onChange} disabled={disabled}
      className="relative h-[16px] w-[28px] shrink-0 rounded-full bg-bg-400 border border-border-400 transition-colors data-[state=checked]:bg-[#257de0] disabled:opacity-50">
      <S.Thumb className="block h-[12px] w-[12px] translate-x-[2px] rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[14px]" />
    </S.Root>
  );
}

export function Segmented({ value, onChange, options, className }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: ReactNode }[]; className?: string;
}) {
  return (
    <T.Root type="single" value={value} onValueChange={(v) => v && onChange(v)}
      className={cn("inline-flex rounded-[5px] bg-bg-400 p-[2px]", className)}>
      {options.map((o) => (
        <T.Item key={o.value} value={o.value}
          className="h-[20px] rounded-[4px] px-2 text-[11.5px] text-text-300 transition-colors hover:text-text-100 data-[state=on]:bg-active data-[state=on]:text-text-000">
          {o.label}
        </T.Item>
      ))}
    </T.Root>
  );
}

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return (
    <input ref={ref}
      className={cn("h-[24px] w-full rounded-[5px] border border-transparent bg-bg-400 px-2.5 text-[11.5px] text-text-100 outline-none",
        "placeholder:text-text-500 focus:border-border-400 selectable", className)}
      {...rest} />
  );
});

export const TextArea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea({ className, ...rest }, ref) {
  return (
    <textarea ref={ref}
      className={cn("w-full rounded-[5px] border border-transparent bg-bg-400 px-2.5 py-1.5 text-[11.5px] text-text-100 outline-none",
        "placeholder:text-text-500 focus:border-border-400 selectable", className)}
      {...rest} />
  );
});

export function Select({ value, onChange, options, className, placeholder }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; className?: string; placeholder?: string;
}) {
  const cur = options.find((o) => o.value === value);
  return (
    <Menu>
      <MenuTrigger asChild>
        <button className={cn("inline-flex h-[24px] min-w-[166px] items-center justify-between gap-2 rounded-[5px] bg-bg-400 px-2.5 text-[11.5px] text-text-100 hover:brightness-110", className)}>
          <span className="truncate">{cur?.label ?? (value || placeholder || "Choose…")}</span>
          <ChevronDownSmall />
        </button>
      </MenuTrigger>
      <MenuContent align="end" className="max-h-[320px] overflow-y-auto">
        {options.map((o) => (
          <MenuItem key={o.value} onSelect={() => onChange(o.value)} checked={o.value === value}>{o.label}</MenuItem>
        ))}
      </MenuContent>
    </Menu>
  );
}

function ChevronDownSmall() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-text-400"><path d="m6 9 6 6 6-6" /></svg>;
}

export function Spinner({ size = 14, className }: { size?: number; className?: string }) {
  return <Loader size={size} className={cn("animate-spin text-text-400", className)} />;
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded-[4px] border border-border-400 bg-bg-300 px-1 py-px font-sans text-[10px] text-text-400">{children}</kbd>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" | "ok" | "warn" | "danger" }) {
  return (
    <span className={cn("inline-flex items-center rounded-[4px] px-1.5 py-[1px] text-[10px] font-medium",
      tone === "neutral" && "bg-bg-400 text-text-300",
      tone === "accent" && "bg-accent-soft text-accent",
      tone === "ok" && "bg-ok/15 text-ok",
      tone === "warn" && "bg-warn-soft text-warn",
      tone === "danger" && "bg-danger-soft text-danger")}>
      {children}
    </span>
  );
}

export { Tt as TooltipPrimitive };
