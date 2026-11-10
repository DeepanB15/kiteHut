import { NavLink } from 'react-router-dom';
import {
  Search,
  FolderOpen,
  Home,
  Zap,
  Heart,
  GitBranch,
  GitPullRequest,
  Bot,
  ShieldCheck,
} from 'lucide-react';

const links = [
  { to: '/', label: 'Analyze', icon: Search },
  { to: '/repositories', label: 'Repositories', icon: FolderOpen },
  { to: '/agent', label: 'Agent Console', icon: Bot },
  { to: '/monitoring', label: 'Guardian Live', icon: ShieldCheck },
];

export default function Sidebar() {
  return (
    <aside className="w-56 bg-gray-900 text-white min-h-screen p-4 flex flex-col">
      <div className="flex items-center gap-2 mb-8 px-2">
        <Home className="h-6 w-6 text-blue-400" />
        <span className="text-xl font-bold">RepoLens</span>
      </div>
      <nav className="flex flex-col gap-1">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-800'
              }`
            }
          >
            <link.icon className="h-4 w-4" />
            {link.label}
          </NavLink>
        ))}

        <div className="mt-4 pt-4 border-t border-gray-700">
          <p className="text-xs text-gray-500 px-3 mb-2">Intelligence</p>
          <NavLink
            to="/github"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-800'
              }`
            }
          >
            <GitPullRequest className="h-4 w-4" />
            GitHub
          </NavLink>
          <NavLink
            to="/analyze-actions"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-800'
              }`
            }
          >
            <Zap className="h-4 w-4" />
            Actions
          </NavLink>
          <NavLink
            to="/health"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-800'
              }`
            }
          >
            <Heart className="h-4 w-4" />
            Health
          </NavLink>
          <NavLink
            to="/root-causes"
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-800'
              }`
            }
          >
            <GitBranch className="h-4 w-4" />
            Root Causes
          </NavLink>
        </div>
      </nav>
    </aside>
  );
}
