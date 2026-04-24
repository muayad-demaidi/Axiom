import { useState } from 'react';
import { Plus, Folder, Upload, MessageSquare, Calendar, MoreHorizontal } from 'lucide-react';
import { CleanProjectView } from './CleanProjectView';

interface Project {
  id: string;
  name: string;
  description: string;
  fileCount: number;
  createdAt: string;
  lastModified: string;
}

export function CleanDashboard() {
  const [projects, setProjects] = useState<Project[]>([
    {
      id: '1',
      name: 'Q1 Sales Analysis',
      description: 'Revenue trends and customer insights',
      fileCount: 3,
      createdAt: '2026-04-15',
      lastModified: '2 hours ago'
    },
    {
      id: '2',
      name: 'Customer Segmentation',
      description: 'Behavioral analysis and cohort studies',
      fileCount: 5,
      createdAt: '2026-04-10',
      lastModified: '1 day ago'
    },
    {
      id: '3',
      name: 'Product Performance',
      description: 'Usage metrics and feature adoption',
      fileCount: 7,
      createdAt: '2026-04-05',
      lastModified: '3 days ago'
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
      lastModified: 'Just now'
    };

    setProjects([newProject, ...projects]);
    setNewProjectName('');
    setNewProjectDesc('');
    setShowNewProject(false);
    setSelectedProject(newProject);
  };

  if (selectedProject) {
    return <CleanProjectView project={selectedProject} onBack={() => setSelectedProject(null)} />;
  }

  return (
    <div className="min-h-screen bg-[#fafaf9]">
      {/* Navigation */}
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-gray-900 rounded-lg flex items-center justify-center">
                <MessageSquare className="w-4 h-4 text-white" strokeWidth={2} />
              </div>
              <h1 className="text-lg font-semibold text-gray-900">DataTalk</h1>
            </div>
            <div className="flex items-center gap-6">
              <button className="text-sm font-medium text-gray-900">Projects</button>
              <button className="text-sm text-gray-600 hover:text-gray-900">Settings</button>
            </div>
          </div>
          <button
            onClick={() => setShowNewProject(true)}
            className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 transition-colors flex items-center gap-2"
          >
            <Plus className="w-4 h-4" strokeWidth={2} />
            New project
          </button>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-8">
          <h2 className="text-2xl font-semibold text-gray-900 mb-2">Your projects</h2>
          <p className="text-gray-600">Analyze and explore your data with AI</p>
        </div>

        {/* Projects Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <button
              key={project.id}
              onClick={() => setSelectedProject(project)}
              className="bg-white rounded-xl border border-gray-200 p-6 text-left hover:shadow-sm hover:border-gray-300 transition-all group"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center group-hover:bg-gray-200 transition-colors">
                  <Folder className="w-5 h-5 text-gray-600" strokeWidth={2} />
                </div>
                <div className="p-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <MoreHorizontal className="w-4 h-4 text-gray-400" strokeWidth={2} />
                </div>
              </div>
              <h3 className="font-semibold text-gray-900 mb-1">{project.name}</h3>
              <p className="text-sm text-gray-600 mb-4 line-clamp-2">{project.description}</p>
              <div className="flex items-center justify-between text-sm text-gray-500">
                <div className="flex items-center gap-1">
                  <Upload className="w-3.5 h-3.5" strokeWidth={2} />
                  <span>{project.fileCount} files</span>
                </div>
                <span>{project.lastModified}</span>
              </div>
            </button>
          ))}
        </div>

        {/* Empty State */}
        {projects.length === 0 && (
          <div className="text-center py-20">
            <div className="w-16 h-16 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Folder className="w-8 h-8 text-gray-400" strokeWidth={2} />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">No projects yet</h3>
            <p className="text-gray-600 mb-6">Create your first project to start analyzing data</p>
            <button
              onClick={() => setShowNewProject(true)}
              className="px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 transition-colors inline-flex items-center gap-2"
            >
              <Plus className="w-4 h-4" strokeWidth={2} />
              Create project
            </button>
          </div>
        )}
      </main>

      {/* New Project Modal */}
      {showNewProject && (
        <div className="fixed inset-0 bg-black/20 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full p-8">
            <h3 className="text-xl font-semibold text-gray-900 mb-6">Create new project</h3>
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Project name
                </label>
                <input
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  placeholder="e.g., Q1 Sales Analysis"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-gray-900 focus:border-transparent outline-none text-gray-900 placeholder-gray-400"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Description <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <textarea
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  placeholder="What will you analyze?"
                  rows={3}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-gray-900 focus:border-transparent outline-none resize-none text-gray-900 placeholder-gray-400"
                />
              </div>
            </div>
            <div className="flex gap-3 mt-8">
              <button
                onClick={() => {
                  setShowNewProject(false);
                  setNewProjectName('');
                  setNewProjectDesc('');
                }}
                className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors text-gray-700 font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateProject}
                disabled={!newProjectName.trim()}
                className="flex-1 px-4 py-2.5 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
