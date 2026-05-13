import { useState } from 'react';
import { Plus, Folder, Settings, Database, Zap, TrendingUp, BarChart3, Activity } from 'lucide-react';
import { AdvancedProjectView } from './AdvancedProjectView';

interface Project {
  id: string;
  name: string;
  description: string;
  datasets: number;
  lastActive: string;
  color: string;
}

export function AdvancedDashboard() {
  const [projects, setProjects] = useState<Project[]>([
    {
      id: '1',
      name: 'Market Trends 2024',
      description: 'Consumer behavior analysis and market forecasting',
      datasets: 12,
      lastActive: '2 min ago',
      color: '#20FF88'
    },
    {
      id: '2',
      name: 'Operational Efficiency',
      description: 'Process optimization and resource allocation',
      datasets: 8,
      lastActive: '1 hour ago',
      color: '#3D5AFE'
    },
    {
      id: '3',
      name: 'Financial Forecasting',
      description: 'Revenue projections and financial modeling',
      datasets: 15,
      lastActive: '3 hours ago',
      color: '#FF6B9D'
    }
  ]);
  const [activeProjectId, setActiveProjectId] = useState<string>('1');
  const [isLoading, setIsLoading] = useState(false);

  const activeProject = projects.find(p => p.id === activeProjectId) || projects[0];

  const handleProjectSwitch = (projectId: string) => {
    if (projectId === activeProjectId) return;

    setIsLoading(true);
    setTimeout(() => {
      setActiveProjectId(projectId);
      setIsLoading(false);
    }, 800);
  };

  return (
    <div className="h-screen flex bg-[#0F0F0F] text-white overflow-hidden">
      {/* Sidebar */}
      <div className="w-72 bg-[#1A1A1A]/80 backdrop-blur-[20px] border-r border-white/5 flex flex-col relative">
        {/* Gradient Border Effect */}
        <div className="absolute inset-y-0 right-0 w-px bg-gradient-to-b from-transparent via-[#20FF88]/20 to-transparent" />

        {/* Logo */}
        <div className="p-6 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-[#20FF88] to-[#3D5AFE] rounded-xl flex items-center justify-center shadow-lg shadow-[#20FF88]/20">
              <Activity className="w-6 h-6 text-[#0F0F0F]" strokeWidth={2.5} />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">DataMind AI</h1>
              <p className="text-xs text-gray-500">Analytics Platform</p>
            </div>
          </div>
        </div>

        {/* Projects Section */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="mb-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Projects</h2>
              <button className="p-1 hover:bg-white/5 rounded-lg transition-colors">
                <Plus className="w-4 h-4 text-gray-400" strokeWidth={2} />
              </button>
            </div>

            <div className="space-y-2">
              {projects.map((project) => (
                <button
                  key={project.id}
                  onClick={() => handleProjectSwitch(project.id)}
                  className={`w-full text-left p-3 rounded-xl transition-all group relative ${
                    activeProjectId === project.id
                      ? 'bg-white/10 shadow-lg'
                      : 'hover:bg-white/5'
                  }`}
                >
                  {activeProjectId === project.id && (
                    <div
                      className="absolute inset-0 rounded-xl opacity-10 blur-xl"
                      style={{ backgroundColor: project.color }}
                    />
                  )}

                  <div className="relative flex items-start gap-3">
                    <div
                      className="w-2 h-2 rounded-full mt-2 flex-shrink-0"
                      style={{
                        backgroundColor: project.color,
                        boxShadow: `0 0 10px ${project.color}80`
                      }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold text-sm truncate">{project.name}</h3>
                        {activeProjectId === project.id && (
                          <div className="flex-shrink-0 px-1.5 py-0.5 bg-[#20FF88]/10 text-[#20FF88] text-[10px] font-bold rounded uppercase">
                            Active
                          </div>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mb-2 line-clamp-1">{project.description}</p>
                      <div className="flex items-center gap-3 text-xs text-gray-600">
                        <div className="flex items-center gap-1">
                          <Database className="w-3 h-3" strokeWidth={2} />
                          <span>{project.datasets}</span>
                        </div>
                        <span>•</span>
                        <span>{project.lastActive}</span>
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* New Project Button */}
          <button className="w-full p-3 border-2 border-dashed border-white/10 rounded-xl hover:border-[#20FF88]/30 hover:bg-[#20FF88]/5 transition-all group">
            <div className="flex items-center justify-center gap-2 text-gray-400 group-hover:text-[#20FF88]">
              <Plus className="w-4 h-4" strokeWidth={2} />
              <span className="text-sm font-medium">New Project</span>
            </div>
          </button>
        </div>

        {/* Settings */}
        <div className="p-4 border-t border-white/5">
          <button className="w-full p-3 hover:bg-white/5 rounded-xl transition-colors flex items-center gap-3 text-gray-400 hover:text-white">
            <Settings className="w-5 h-5" strokeWidth={2} />
            <span className="text-sm font-medium">Settings</span>
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="w-16 h-16 bg-gradient-to-br from-[#20FF88]/20 to-[#3D5AFE]/20 rounded-2xl flex items-center justify-center mx-auto mb-4 backdrop-blur-xl border border-white/10 animate-pulse">
                <Zap className="w-8 h-8 text-[#20FF88]" strokeWidth={2} />
              </div>
              <h3 className="text-lg font-semibold mb-2">Loading Context</h3>
              <p className="text-sm text-gray-500">Switching to {projects.find(p => p.id === activeProjectId)?.name}</p>
              <div className="mt-4 flex items-center justify-center gap-1">
                <div className="w-2 h-2 bg-[#20FF88] rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-[#3D5AFE] rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                <div className="w-2 h-2 bg-[#FF6B9D] rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
              </div>
            </div>
          </div>
        ) : (
          <AdvancedProjectView project={activeProject} />
        )}
      </div>
    </div>
  );
}
