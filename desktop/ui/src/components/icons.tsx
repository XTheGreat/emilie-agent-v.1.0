// One place for every icon, so a renamed lucide icon only needs fixing here.
import * as L from "lucide-react";
import type { ComponentType, SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number; strokeWidth?: number };
const wrap = (C: ComponentType<any>) => (p: P) => <C size={16} strokeWidth={1.75} aria-hidden {...p} />;

export const Plus = wrap(L.Plus);
export const Search = wrap(L.Search);
export const FolderIcon = wrap(L.Folder);
export const FolderOpen = wrap(L.FolderOpen);
export const FolderPlus = wrap(L.FolderPlus);
export const Settings = wrap(L.Settings);
export const ChevronDown = wrap(L.ChevronDown);
export const ChevronRight = wrap(L.ChevronRight);
export const ChevronLeft = wrap(L.ChevronLeft);
export const ChevronUp = wrap(L.ChevronUp);
export const Menu = wrap(L.Menu);
export const PanelLeft = wrap(L.PanelLeft);
export const ArrowLeft = wrap(L.ArrowLeft);
export const ArrowRight = wrap(L.ArrowRight);
export const ArrowUp = wrap(L.ArrowUp);
export const Terminal = wrap(L.SquareTerminal);
export const Globe = wrap(L.Globe);
export const FileIcon = wrap(L.File);
export const FileText = wrap(L.FileText);
export const FileCode = wrap(L.FileCode);
export const FileDiff = wrap(L.FileDiff);
export const Square = wrap(L.Square);
export const Mic = wrap(L.Mic);
export const MicOff = wrap(L.MicOff);
export const Paperclip = wrap(L.Paperclip);
export const ImageIcon = wrap(L.Image);
export const Camera = wrap(L.Camera);
export const Check = wrap(L.Check);
export const X = wrap(L.X);
export const Copy = wrap(L.Copy);
export const Pencil = wrap(L.Pencil);
export const Trash = wrap(L.Trash);
export const Ellipsis = wrap(L.Ellipsis);
export const Book = wrap(L.BookOpen);
export const Plug = wrap(L.Plug);
export const Clock = wrap(L.Clock);
export const Shield = wrap(L.Shield);
export const User = wrap(L.User);
export const Palette = wrap(L.Palette);
export const Cpu = wrap(L.Cpu);
export const Volume = wrap(L.Volume2);
export const Sparkles = wrap(L.Sparkles);
export const Code = wrap(L.Code);
export const MessageSquare = wrap(L.MessageSquare);
export const Play = wrap(L.Play);
export const Refresh = wrap(L.RefreshCw);
export const External = wrap(L.ExternalLink);
export const Eye = wrap(L.Eye);
export const Loader = wrap(L.LoaderCircle);
export const CircleCheck = wrap(L.CircleCheck);
export const CircleX = wrap(L.CircleX);
export const Alert = wrap(L.TriangleExclamationPoint);
export const AlertCircle = wrap(L.CircleExclamationPoint);
export const Info = wrap(L.Info);
export const Sliders = wrap(L.SlidersHorizontal);
export const Laptop = wrap(L.Laptop);
export const GitBranch = wrap(L.GitBranch);
export const Rewind = wrap(L.Rewind);
export const RotateCcw = wrap(L.RotateCcw);
export const Wand = wrap(L.WandSparkles);
export const ListTodo = wrap(L.ListTodo);
export const Activity = wrap(L.Activity);
export const Circle = wrap(L.Circle);
export const CircleDot = wrap(L.CircleDot);
export const Hammer = wrap(L.Hammer);
export const Wrench = wrap(L.Wrench);
export const Bot = wrap(L.Bot);
export const PanelRight = wrap(L.PanelRight);
export const Maximize = wrap(L.Maximize2);
export const Minimize = wrap(L.Minimize2);
export const Box = wrap(L.Box);
export const Layers = wrap(L.Layers);
export const Archive = wrap(L.Archive);
export const Download = wrap(L.Download);
export const Video = wrap(L.Video);
export const Phone = wrap(L.Phone);
export const PhoneOff = wrap(L.PhoneOff);
export const Brain = wrap(L.Brain);
export const Zap = wrap(L.Zap);
export const AtSign = wrap(L.AtSign);
export const Slash = wrap(L.Slash);
export const Keyboard = wrap(L.Keyboard);
export const Power = wrap(L.Power);
export const Lock = wrap(L.Lock);
export const Key = wrap(L.KeyRound);
export const ScrollText = wrap(L.ScrollText);
export const Library = wrap(L.Library);
export const Puzzle = wrap(L.Puzzle);
export const Ban = wrap(L.Ban);
export const Gauge = wrap(L.Gauge);
export const FolderTree = wrap(L.FolderTree);
export const Undo = wrap(L.Undo2);
export const Pause = wrap(L.Pause);
export const Flower = wrap(L.Flower2);
export const Monitor = wrap(L.Monitor);
export const Bug = wrap(L.Bug);
export const Pin = wrap(L.Pin);
export const PinOff = wrap(L.PinOff);
export const Split = wrap(L.Split);
export const CircleEllipsis = wrap(L.CircleEllipsis);
export const CircleDashed = wrap(L.CircleDashed);
export const Presentation = wrap(L.Presentation);
export const Sheet = wrap(L.FileSpreadsheet);
export const Workflow = wrap(L.Workflow);
export const NotebookPen = wrap(L.NotebookPen);
export const AppWindow = wrap(L.AppWindow);
export const LayoutGrid = wrap(L.LayoutGrid);
export const ArrowUpDown = wrap(L.ArrowUpDown);
export const ListFilter = wrap(L.ListFilter);
export const CodeXml = wrap(L.CodeXml);
export const CircleHelp = wrap(L.CircleHelp);
export const LogOut = wrap(L.LogOut);
export const Blocks = wrap(L.Blocks);
export const MessageCircle = wrap(L.MessageCircle);
export const Bell = wrap(L.Bell);
export const ListIcon = wrap(L.List);
export const Expand = wrap(L.Maximize2);
export const Shrink = wrap(L.Minimize2);
export const CornerDownLeft = wrap(L.CornerDownLeft);
export const MessageCirclePlus = wrap(L.MessageCirclePlus);
export const FilePlain = wrap(L.File);
export const Files = wrap(L.Files);
export const Table = wrap(L.Sheet);
export const ChartColumn = wrap(L.ChartNoAxesColumn);
export const Blend = wrap(L.Blend);
// the project panels (Git, Scripts, Problems, Tests, HTTP, Ports, Notes, Database)
export const GitCommit = wrap(L.GitCommitHorizontal);
export const GitMerge = wrap(L.GitMerge);
export const GitBranchPlus = wrap(L.GitBranchPlus);
export const GitPullRequest = wrap(L.GitPullRequest);
export const Flask = wrap(L.FlaskConical);
export const SendIcon = wrap(L.SendHorizontal);
export const Port = wrap(L.EthernetPort);
export const StickyNote = wrap(L.StickyNote);
export const Database = wrap(L.Database);
export const StopCircle = wrap(L.CircleStop);
export const Minus = wrap(L.Minus);
export const PullIcon = wrap(L.ArrowDownToLine);
export const PushIcon = wrap(L.ArrowUpFromLine);
export const FetchIcon = wrap(L.CloudDownload);
export const Package = wrap(L.Package);
export const Server = wrap(L.Server);
export const TableIcon = wrap(L.Table2);
export const Braces = wrap(L.Braces);
export const ListChecks = wrap(L.ListChecks);
export const Tag = wrap(L.Tag);
export const CheckBig = wrap(L.CircleCheckBig);
export const CircleSlash = wrap(L.CircleSlash);
export const RotateCw = wrap(L.RotateCw);

// ------------------------------------------------------------------ icons drawn like the Claude Code desktop app (16px grid)
function Svg({ size = 13, strokeWidth = 1.35, children, ...p }: P & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={strokeWidth}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden {...p}>{children}</svg>
  );
}

/** three lines, each a little shorter */
export const MenuLines = (p: P) => <Svg {...p}><path d="M2.5 4h11M2.5 8h9.5M2.5 12h7.5" /></Svg>;
/** a window with the side panel marked */
export const SidebarToggle = (p: P) => <Svg {...p}><rect x="2" y="3" width="12" height="10" rx="2" /><path d="M5.25 5.75v4.5" strokeWidth={1.8} /></Svg>;
export const ChevL = (p: P) => <Svg {...p}><path d="m10 3.5-4.5 4.5 4.5 4.5" /></Svg>;
export const ChevR = (p: P) => <Svg {...p}><path d="m6 3.5 4.5 4.5L6 12.5" /></Svg>;
export const ChevD = (p: P) => <Svg {...p}><path d="m4 6 4 4 4-4" /></Svg>;
/** the "Chat" tab: a speech bubble with a small one in front */
export const ChatBubble = (p: P) => (
  <Svg {...p}>
    <path d="M12.2 7.6A5 5 0 1 0 4.5 11.4L3 13.6l3.1-.9" />
    <circle cx="11" cy="11" r="2.4" />
  </Svg>
);
/** "</>" — the "Code" tab */
export const CodeBrackets = (p: P) => <Svg {...p}><path d="M5.2 4.6 2 8l3.2 3.4M10.8 4.6 14 8l-3.2 3.4M9.1 3.2 6.9 12.8" /></Svg>;
export const LaptopIcon = (p: P) => <Svg {...p}><rect x="3" y="3.5" width="10" height="7" rx="1.2" /><path d="M1.5 12.5h13" /></Svg>;
export const LaptopOff = (p: P) => <Svg {...p}><rect x="3" y="3.5" width="10" height="7" rx="1.2" /><path d="M1.5 12.5h13M2 2l12 12" /></Svg>;
export const FolderSm = (p: P) => <Svg {...p}><path d="M2 4.6c0-.6.5-1.1 1.1-1.1h2.8l1.4 1.5h5.6c.6 0 1.1.5 1.1 1.1v5.8c0 .6-.5 1.1-1.1 1.1H3.1c-.6 0-1.1-.5-1.1-1.1Z" /></Svg>;
/** ↵ — send */
export const ReturnKey = (p: P) => <Svg {...p}><path d="M13 3.5v4.2c0 1-.8 1.8-1.8 1.8H3.5M6.3 6.7 3.5 9.5l2.8 2.8" /></Svg>;
export const PlusSm = (p: P) => <Svg {...p}><path d="M8 2.75v10.5M2.75 8h10.5" /></Svg>;
export const SearchSm = (p: P) => <Svg {...p}><circle cx="7" cy="7" r="4.3" /><path d="m10.2 10.2 3.3 3.3" /></Svg>;
/** Projects: a box with a lid */
export const ProjectsIcon = (p: P) => <Svg {...p}><path d="M4.5 2.5h7M3.5 4.75h9" /><rect x="2.5" y="7" width="11" height="6.5" rx="1.6" /></Svg>;
/** Artifacts: two cards */
export const ArtifactsIcon = (p: P) => <Svg {...p}><rect x="5.5" y="2.5" width="8" height="8.5" rx="1.5" /><path d="M10.5 11v1c0 .8-.7 1.5-1.5 1.5H4c-.8 0-1.5-.7-1.5-1.5V7c0-.8.7-1.5 1.5-1.5h1.5" /></Svg>;
/** Customize: a case */
export const CustomizeIcon = (p: P) => <Svg {...p}><rect x="2" y="5" width="12" height="8" rx="1.6" /><path d="M6 5V3.8c0-.5.4-.8.8-.8h2.4c.5 0 .8.4.8.8V5" /></Svg>;
export const Dots = (p: P) => <Svg {...p} strokeWidth={0}><circle cx="3.5" cy="8" r="1.05" fill="currentColor" /><circle cx="8" cy="8" r="1.05" fill="currentColor" /><circle cx="12.5" cy="8" r="1.05" fill="currentColor" /></Svg>;
export const Prompt = (p: P) => <Svg {...p}><path d="m3 4.5 3.5 3.5L3 11.5M8.5 12h4.5" /></Svg>;
export const GlobeSm = (p: P) => <Svg {...p}><circle cx="8" cy="8" r="5.6" /><path d="M2.4 8h11.2M8 2.4c1.5 1.6 2.3 3.5 2.3 5.6S9.5 12 8 13.6M8 2.4C6.5 4 5.7 5.9 5.7 8s.8 4 2.3 5.6" /></Svg>;
export const MicSm = (p: P) => <Svg {...p}><rect x="5.75" y="2" width="4.5" height="7.5" rx="2.25" /><path d="M3.5 7.5a4.5 4.5 0 0 0 9 0M8 12v2" /></Svg>;
export const GearSm = (p: P) => (
  <Svg {...p}>
    <circle cx="8" cy="8" r="2" />
    <path d="M8 1.8v1.4M8 12.8v1.4M14.2 8h-1.4M3.2 8H1.8M12.4 3.6l-1 1M4.6 11.4l-1 1M12.4 12.4l-1-1M4.6 4.6l-1-1" />
    <circle cx="8" cy="8" r="4.6" />
  </Svg>
);
/** a box with ± (the Changes pane) */
export const DiffBox = (p: P) => <Svg {...p}><rect x="2.5" y="2.5" width="11" height="11" rx="2" /><path d="M8 5v4M6 7h4M6 11h4" /></Svg>;
export const BranchSm = (p: P) => <Svg {...p}><circle cx="4.5" cy="3.8" r="1.5" /><circle cx="4.5" cy="12.2" r="1.5" /><circle cx="11.5" cy="5.5" r="1.5" /><path d="M4.5 5.3v5.4M11.5 7c0 2.5-3.5 2.2-6.4 4" /></Svg>;
/** three small panels and a plus: the title bar's "More panels" */
export const PanelsPlus = (p: P) => (
  <Svg {...p}>
    <rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1.2" /><rect x="9" y="2.5" width="4.5" height="4.5" rx="1.2" />
    <rect x="2.5" y="9" width="4.5" height="4.5" rx="1.2" /><path d="M11.25 9.1v4.3M9.1 11.25h4.3" />
  </Svg>
);

// kept for older call sites
export const ChatSpark = ChatBubble;
export const CodeTab = CodeBrackets;
