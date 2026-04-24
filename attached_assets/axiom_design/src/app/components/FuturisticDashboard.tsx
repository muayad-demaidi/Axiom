import { useState } from 'react';
import { Sparkles, Brain, Zap, TrendingUp, Database, Upload, MessageSquare, BarChart3, Activity, Cpu, Network, FileSearch } from 'lucide-react';
import { FuturisticProjectView } from './FuturisticProjectView';

interface Project {
  id: string;
  name: string;
  description: string;
  fileCount: number;
  createdAt: string;
  status: 'active' | 'processing' | 'completed';
  insights: number;
}

export function FuturisticDashboard() {
  const [projects, setProjects] = useState<Project[]>([
    {
      id: '1',
      name: 'Q1 Revenue Analysis',
      description: 'Deep dive into quarterly sales patterns and market trends',
      fileCount: 12,
      createdAt: '2026-04-15',
      status: 'active',
      insights: 47
    },
    {
      id: '2',
      name: 'Customer Behavior Study',
      description: 'ML-powered segmentation and predictive analytics',
      fileCount: 8,
      createdAt: '2026-04-10',
      status: 'completed',
      insights: 23
    }
  ]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [showNewProject, setShowNewProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');

  const handleCreateProject = () => {
    if (!newProjectName.trim()) return;

    const newProject: Project = {
      id: Date.now().toString(),
      name: newProjectName,
      description: newProjectDesc,
      fileCount: 0,
      createdAt: new Date().toISOString().split('T')[0],
      status: 'active',
      insights: 0
    };

    setProjects([newProject, ...projects]);
    setNewProjectName('');
    setNewProjectDesc('');
    setShowNewProject(false);
    setSelectedProject(newProject);
  };

  if (selectedProject) {
    return <FuturisticProjectView project={selectedProject} onBack={() => setSelectedProject(null)} />;
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white relative overflow-hidden">
      {/* Animated Background */}
      <div className="fixed inset-0 gradient-mesh opacity-50" />
      <div className="fixed inset-0 neural-grid opacity-20" />

      {/* Floating Orbs */}
      <div className="fixed top-20 right-20 w-96 h-96 bg-purple-500/20 rounded-full blur-[128px] animate-pulse" />
      <div className="fixed bottom-20 left-20 w-96 h-96 bg-blue-500/20 rounded-full blur-[128px] animate-pulse" style={{ animationDelay: '1s' }} />
      <div className="fixed top-1/2 left-1/2 w-96 h-96 bg-cyan-500/10 rounded-full blur-[128px] animate-pulse" style={{ animationDelay: '2s' }} />

      {/* Content */}
      <div className="relative z-10">
        {/* Navigation */}
        <nav className="glass-panel-strong border-b border-white/10 sticky top-0 z-50">
          <div className="max-w-[1600px] mx-auto px-8 py-4 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="relative">
                <div className="w-12 h-12 bg-gradient-to-br from-purple-500 via-blue-500 to-cyan-500 rounded-2xl flex items-center justify-center neon-glow-purple">
                  <Brain className="w-7 h-7 text-white" />
                </div>
                <div className="absolute -top-1 -right-1 w-3 h-3 bg-cyan-400 rounded-full glow-pulse" />
              </div>
              <div>
                <h1 className="text-2xl font-bold gradient-text tracking-tight">DataMind AI</h1>
                <p className="text-xs text-gray-400">Neural Data Platform</p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <button className="px-4 py-2 glass-panel rounded-xl hover:bg-white/10 transition-all flex items-center gap-2 text-sm">
                <Activity className="w-4 h-4 text-cyan-400" />
                <span className="text-gray-300">System Active</span>
              </button>
              <button
                onClick={() => setShowNewProject(true)}
                className="px-6 py-2.5 bg-gradient-to-r from-purple-600 to-blue-600 rounded-xl hover:shadow-lg hover:shadow-purple-500/50 transition-all flex items-center gap-2 font-medium neon-glow-purple"
              >
                <Sparkles className="w-4 h-4" />
                New Analysis
              </button>
            </div>
          </div>
        </nav>

        <main className="max-w-[1600px] mx-auto px-8 py-12">
          {/* Hero Section */}
          {projects.length === 0 && !showNewProject && (
            <div className="text-center py-24">
              <div className="relative inline-block mb-8">
                <div className="w-32 h-32 bg-gradient-to-br from-purple-500/20 via-blue-500/20 to-cyan-500/20 rounded-[2.5rem] flex items-center justify-center glass-panel-strong neon-glow-purple float-animation">
                  <Brain className="w-16 h-16 text-purple-300" />
                </div>
                <div className="absolute -top-2 -right-2 w-8 h-8 bg-cyan-400 rounded-full glow-pulse flex items-center justify-center">
                  <Zap className="w-4 h-4 text-white" />
                </div>
              </div>
              <h2 className="text-6xl font-bold mb-4 gradient-text">Think at the Speed of AI</h2>
              <p className="text-xl text-gray-400 mb-12 max-w-2xl mx-auto">
                Upload your data. Ask questions. Get insights instantly.
                <br />
                <span className="text-purple-400">Let intelligence do the heavy lifting.</span>
              </p>
              <button
                onClick={() => setShowNewProject(true)}
                className="px-8 py-4 bg-gradient-to-r from-purple-600 via-blue-600 to-cyan-600 rounded-2xl hover:shadow-2xl hover:shadow-purple-500/50 transition-all inline-flex items-center gap-3 text-lg font-medium neon-glow-purple group"
              >
                <Sparkles className="w-6 h-6 group-hover:rotate-180 transition-transform duration-500" />
                Start Your First Analysis
                <Zap className="w-5 h-5" />
              </button>

              {/* Feature Cards */}
              <div className="grid grid-cols-3 gap-6 mt-20 max-w-4xl mx-auto">
                {[
                  { icon: MessageSquare, title: 'Conversational AI', desc: 'Talk to your data naturally' },
                  { icon: TrendingUp, title: 'Auto Insights', desc: 'AI finds patterns for you' },
                  { icon: Cpu, title: 'Real-time Processing', desc: 'Instant analysis, no waiting' }
                ].map((feature, i) => (
                  <div key={i} className="glass-panel rounded-2xl p-6 hover:bg-white/10 transition-all data-card group">
                    <feature.icon className="w-8 h-8 text-cyan-400 mb-4 group-hover:scale-110 transition-transform" />
                    <h3 className="font-semibold mb-2">{feature.title}</h3>
                    <p className="text-sm text-gray-400">{feature.desc}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* New Project Modal */}
          {showNewProject && (
            <div className="fixed inset-0 bg-black/80 backdrop-blur-xl flex items-center justify-center z-50 p-4">
              <div className="glass-panel-strong rounded-3xl shadow-2xl max-w-2xl w-full p-10 neon-glow-purple">
                <div className="flex items-center gap-4 mb-8">
                  <div className="w-14 h-14 bg-gradient-to-br from-purple-500 to-blue-500 rounded-2xl flex items-center justify-center neon-glow-purple">
                    <Brain className="w-7 h-7 text-white" />
                  </div>
                  <div>
                    <h3 className="text-3xl font-bold gradient-text">New Analysis Project</h3>
                    <p className="text-gray-400 text-sm">Create a neural workspace for your data</p>
                  </div>
                </div>

                <div className="space-y-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-3">Project Name</label>
                    <input
                      type="text"
                      value={newProjectName}
                      onChange={(e) => setNewProjectName(e.target.value)}
                      placeholder="e.g., Revenue Forecasting Q2"
                      className="w-full px-5 py-4 glass-panel border border-white/10 rounded-2xl focus:ring-2 focus:ring-purple-500 focus:border-transparent outline-none text-white placeholder-gray-500 transition-all"
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-3">Description</label>
                    <textarea
                      value={newProjectDesc}
                      onChange={(e) => setNewProjectDesc(e.target.value)}
                      placeholder="What insights are you looking for?"
                      rows={4}
                      className="w-full px-5 py-4 glass-panel border border-white/10 rounded-2xl focus:ring-2 focus:ring-purple-500 focus:border-transparent outline-none resize-none text-white placeholder-gray-500 transition-all"
                    />
                  </div>
                </div>

                <div className="flex gap-4 mt-10">
                  <button
                    onClick={() => {
                      setShowNewProject(false);
                      setNewProjectName('');
                      setNewProjectDesc('');
                    }}
                    className="flex-1 px-6 py-4 glass-panel border border-white/10 rounded-2xl hover:bg-white/10 transition-all font-medium"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleCreateProject}
                    disabled={!newProjectName.trim()}
                    className="flex-1 px-6 py-4 bg-gradient-to-r from-purple-600 to-blue-600 rounded-2xl hover:shadow-2xl hover:shadow-purple-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed font-medium neon-glow-purple flex items-center justify-center gap-2"
                  >
                    <Sparkles className="w-5 h-5" />
                    Create Project
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Projects Grid */}
          {projects.length > 0 && (
            <div>
              {/* Stats Overview */}
              <div className="grid grid-cols-4 gap-6 mb-12">
                {[
                  { label: 'Active Projects', value: projects.length, icon: Database, color: 'purple' },
                  { label: 'Total Insights', value: projects.reduce((acc, p) => acc + p.insights, 0), icon: Brain, color: 'blue' },
                  { label: 'Files Analyzed', value: projects.reduce((acc, p) => acc + p.fileCount, 0), icon: FileSearch, color: 'cyan' },
                  { label: 'Neural Uptime', value: '99.9%', icon: Network, color: 'purple' }
                ].map((stat, i) => (
                  <div key={i} className="glass-panel rounded-2xl p-6 data-card group hover:scale-105 transition-transform">
                    <div className="flex items-center justify-between mb-4">
                      <stat.icon className={`w-6 h-6 text-${stat.color}-400`} />
                      <div className={`w-2 h-2 bg-${stat.color}-400 rounded-full glow-pulse`} />
                    </div>
                    <div className="text-3xl font-bold mb-1 gradient-text">{stat.value}</div>
                    <div className="text-sm text-gray-400">{stat.label}</div>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between mb-8">
                <h2 className="text-3xl font-bold gradient-text">Neural Workspaces</h2>
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <Activity className="w-4 h-4 text-green-400" />
                  <span>All systems operational</span>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {projects.map((project) => (
                  <button
                    key={project.id}
                    onClick={() => setSelectedProject(project)}
                    className="glass-panel rounded-3xl p-8 text-left border border-white/10 hover:border-purple-500/50 transition-all group data-card relative overflow-hidden"
                  >
                    <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-purple-500/10 to-blue-500/10 rounded-bl-[4rem] blur-2xl" />

                    <div className="relative z-10">
                      <div className="flex items-start justify-between mb-6">
                        <div className="flex items-center gap-4">
                          <div className="w-14 h-14 bg-gradient-to-br from-purple-500/20 to-blue-500/20 rounded-2xl flex items-center justify-center glass-panel group-hover:scale-110 transition-transform neon-glow-purple">
                            <BarChart3 className="w-7 h-7 text-purple-300" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <h3 className="text-xl font-bold">{project.name}</h3>
                              {project.status === 'active' && (
                                <div className="w-2 h-2 bg-cyan-400 rounded-full glow-pulse" />
                              )}
                            </div>
                            <p className="text-sm text-gray-400">{project.createdAt}</p>
                          </div>
                        </div>
                      </div>

                      <p className="text-gray-300 mb-6">{project.description}</p>

                      <div className="flex items-center gap-6 text-sm">
                        <div className="flex items-center gap-2">
                          <Upload className="w-4 h-4 text-purple-400" />
                          <span className="text-gray-300">{project.fileCount} files</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Brain className="w-4 h-4 text-blue-400" />
                          <span className="text-gray-300">{project.insights} insights</span>
                        </div>
                        <div className={`ml-auto px-3 py-1 rounded-full text-xs font-medium ${
                          project.status === 'active' ? 'bg-cyan-500/20 text-cyan-300' :
                          project.status === 'processing' ? 'bg-purple-500/20 text-purple-300' :
                          'bg-green-500/20 text-green-300'
                        }`}>
                          {project.status}
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
