import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDuration(ms: number): string {
  if (ms < 1) {
    return `${(ms * 1000).toFixed(0)} µs`;
  }
  if (ms < 1000) {
    return `${ms.toFixed(2)} ms`;
  }
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatTimestamp(ns: number): string {
  if (!ns) return '--:--:--';
  const date = new Date(ns / 1_000_000);
  return date.toISOString().substring(11, 23);
}

export function getSpanTheme(name: string): {
  color: string;
  bg: string;
  border: string;
  glow: string;
  icon: string;
  label: string;
} {
  switch (name) {
    case 'flight_recorder':
      return {
        color: 'text-hud-cyan',
        bg: 'bg-hud-cyan/15',
        border: 'border-hud-cyan/40',
        glow: 'shadow-glow-cyan',
        icon: '⚡',
        label: 'ROOT FLIGHT RECORDER',
      };
    case 'detect':
      return {
        color: 'text-cyan-400',
        bg: 'bg-cyan-500/20',
        border: 'border-cyan-500/40',
        glow: 'shadow-glow-cyan',
        icon: '📷',
        label: '1. DETECT (CV)',
      };
    case 'tag_pose':
      return {
        color: 'text-blue-400',
        bg: 'bg-blue-500/20',
        border: 'border-blue-500/40',
        glow: 'shadow-glow-cyan',
        icon: '🎯',
        label: '2. TAG POSE (APRILTAG)',
      };
    case 'update_twin':
      return {
        color: 'text-indigo-400',
        bg: 'bg-indigo-500/20',
        border: 'border-indigo-500/40',
        glow: 'shadow-glow-violet',
        icon: '🔄',
        label: '3. UPDATE DIGITAL TWIN',
      };
    case 'extract_params':
      return {
        color: 'text-amber-400',
        bg: 'bg-amber-500/20',
        border: 'border-amber-500/40',
        glow: 'shadow-glow-amber',
        icon: '⚙️',
        label: '4. EXTRACT PARAMS',
      };
    case 'scrape':
      return {
        color: 'text-purple-400',
        bg: 'bg-purple-500/25',
        border: 'border-purple-500/50',
        glow: 'shadow-glow-violet',
        icon: '🌐',
        label: '5. BRIGHT DATA ENRICHMENT',
      };
    case 'patch_spec':
      return {
        color: 'text-emerald-400',
        bg: 'bg-emerald-500/20',
        border: 'border-emerald-500/40',
        glow: 'shadow-glow-emerald',
        icon: '📝',
        label: '6. HOT-SWAP PATCH SPEC',
      };
    case 'test':
      return {
        color: 'text-teal-400',
        bg: 'bg-teal-500/20',
        border: 'border-teal-500/40',
        glow: 'shadow-glow-cyan',
        icon: '🛡️',
        label: '7. GATE SIM VALIDATION',
      };
    case 'approve':
      return {
        color: 'text-emerald-300',
        bg: 'bg-emerald-400/20',
        border: 'border-emerald-400/50',
        glow: 'shadow-glow-emerald',
        icon: '💎',
        label: '8. AUTO FAST APPROVAL',
      };
    case 'skill_exec':
      return {
        color: 'text-hud-cyan',
        bg: 'bg-hud-cyan/20',
        border: 'border-hud-cyan/50',
        glow: 'shadow-glow-cyan',
        icon: '▶',
        label: '9. MUJOCO SKILL EXEC',
      };
    default:
      return {
        color: 'text-slate-300',
        bg: 'bg-slate-700/30',
        border: 'border-slate-600/40',
        glow: 'none',
        icon: '⏱️',
        label: name.toUpperCase(),
      };
  }
}
