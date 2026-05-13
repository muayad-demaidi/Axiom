import { useState } from 'react';
import { Plus, Folder, ChevronDown, ChevronRight, FileText, Database, MessageSquare, Moon, Sun, Home } from 'lucide-react';
import { ProfessionalProjectView } from './ProfessionalProjectView';

interface Project {
  id: string;
  name: string;
  datasets: Dataset[];
  chatHistory: ChatHistoryItem[];
  isExpanded: boolean;
}

interface Dataset {
  id: string;
  name: string;
  type: 'csv' | 'excel' | 'sql';
  size: string;
}

interface ChatHistoryItem {
  id: string;
  title: string;
  timestamp: string;
}

export function ProfessionalDashboard({ onGoHome }: { onGoHome?: () => void }) {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [projects, setProjects] = useState<Project[]>([
    {
      id: '1',
      name: 'Q3 Financials',
      isExpanded: true,
      datasets: [
        { id: 'd1', name: 'revenue_q3.csv', type: 'csv', size: '2.3 MB' },
        { id: 'd2', name: 'expenses.xlsx', type: 'excel', size: '1.8 MB' }
      ],
      chatHistory: [
        { id: 'c1', title: 'Revenue trend analysis', timestamp: '2 hours ago' },
        { id: 'c2', title: 'Cost breakdown by department', timestamp: '5 hours ago' }
      ]
    },
    {
      id: '2',
      name: 'User Behavior',
      isExpanded: false,
      datasets: [
        { id: 'd3', name: 'user_sessions.csv', type: 'csv', size: '4.1 MB' },
        { id: 'd4', name: 'clickstream_data.csv', type: 'csv', size: '6.7 MB' }
      ],
      chatHistory: [
        { id: 'c3', title: 'Session duration patterns', timestamp: '1 day ago' }
      ]
    },
    {
      id: '3',
      name: 'Market Trends 2024',
      isExpanded: false,
      datasets: [
        { id: 'd5', name: 'market_data.csv', type: 'csv', size: '3.2 MB' }
      ],
      chatHistory: [
        { id: 'c4', title: 'Industry growth analysis', timestamp: '2 days ago' }
      ]
    }
  ]);
  const [activeProjectId, setActiveProjectId] = useState<string>('1');

  const activeProject = projects.find(p => p.id === activeProjectId) || projects[0];

  const toggleProject = (projectId: string) => {
    setProjects(projects.map(p =>
      p.id === projectId ? { ...p, isExpanded: !p.isExpanded } : p
    ));
  };

  const bgColor = isDarkMode ? 'bg-[#111827]' : 'bg-[#FFFAF0]';
  const panelBg = isDarkMode ? 'bg-[#1F2937]' : 'bg-[#FFF8E7]';
  const textPrimary = isDarkMode ? 'text-white' : 'text-gray-900';
  const textSecondary = isDarkMode ? 'text-gray-400' : 'text-gray-700';
  const textTertiary = isDarkMode ? 'text-gray-500' : 'text-gray-600';
  const borderColor = isDarkMode ? 'border-gray-700' : 'border-[#F5E6D3]';
  const hoverBg = isDarkMode ? 'hover:bg-gray-800' : 'hover:bg-[#FFF5DC]';
  const activeBg = isDarkMode ? 'bg-gray-800' : 'bg-[#FFEFD5]';

  return (
    <div className={`h-screen flex ${bgColor} ${textPrimary}`}>
      {/* Sidebar - 20% width */}
      <div className={`w-80 ${panelBg} border-r ${borderColor} flex flex-col`}>
        {/* Header */}
        <div className="p-4 border-b border-gray-700">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Database className="w-5 h-5 text-[#2563EB]" strokeWidth={2} />
              <h1 className="text-sm font-semibold">DataAnalyst AI</h1>
            </div>
            <div className="flex items-center gap-1">
              {onGoHome && (
                <button
                  onClick={onGoHome}
                  className={`p-2 rounded-md ${hoverBg} transition-colors`}
                  title="Go to Home"
                >
                  <Home className={`w-4 h-4 ${isDarkMode ? 'text-gray-400' : 'text-gray-600'}`} strokeWidth={2} />
                </button>
              )}
              <button
                onClick={() => setIsDarkMode(!isDarkMode)}
                className={`p-2 rounded-md ${hoverBg} transition-colors`}
              >
                {isDarkMode ? (
                  <Sun className="w-4 h-4 text-gray-400" strokeWidth={2} />
                ) : (
                  <Moon className="w-4 h-4 text-gray-600" strokeWidth={2} />
                )}
              </button>
            </div>
          </div>
          <button className="w-full px-4 py-2 bg-[#2563EB] text-white text-sm font-medium rounded-md hover:bg-[#1d4ed8] transition-colors flex items-center justify-center gap-2">
            <Plus className="w-4 h-4" strokeWidth={2} />
            New Project
          </button>
        </div>

        {/* Projects Section */}
        <div className="flex-1 overflow-y-auto p-4">
          <h2 className={`text-xs font-semibold uppercase tracking-wider mb-3 ${textTertiary}`}>
            Projects
          </h2>

          <div className="space-y-1">
            {projects.map((project) => (
              <div key={project.id}>
                {/* Project Header */}
                <button
                  onClick={() => {
                    setActiveProjectId(project.id);
                    if (!project.isExpanded) {
                      toggleProject(project.id);
                    }
                  }}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                    activeProjectId === project.id
                      ? activeBg
                      : hoverBg
                  }`}
                >
                  <div
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleProject(project.id);
                    }}
                    className="flex-shrink-0 cursor-pointer"
                  >
                    {project.isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-gray-400" strokeWidth={2} />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-gray-400" strokeWidth={2} />
                    )}
                  </div>
                  <Folder className={`w-4 h-4 flex-shrink-0 ${activeProjectId === project.id ? 'text-[#2563EB]' : 'text-gray-400'}`} strokeWidth={2} />
                  <span className="flex-1 text-left truncate font-medium">{project.name}</span>
                </button>

                {/* Project Contents */}
                {project.isExpanded && (
                  <div className="ml-6 mt-1 space-y-2">
                    {/* Datasets */}
                    <div>
                      <h3 className={`text-xs font-medium mb-1 px-3 ${textTertiary}`}>Datasets</h3>
                      <div className="space-y-0.5">
                        {project.datasets.map((dataset) => (
                          <button
                            key={dataset.id}
                            className={`w-full flex items-center gap-2 px-3 py-1.5 rounded text-xs ${hoverBg} transition-colors`}
                          >
                            <FileText className="w-3.5 h-3.5 text-gray-400" strokeWidth={2} />
                            <span className={`flex-1 text-left truncate ${textSecondary}`}>{dataset.name}</span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Chat History */}
                    <div>
                      <h3 className={`text-xs font-medium mb-1 px-3 ${textTertiary}`}>Chat History</h3>
                      <div className="space-y-0.5">
                        {project.chatHistory.map((chat) => (
                          <button
                            key={chat.id}
                            className={`w-full flex items-start gap-2 px-3 py-1.5 rounded text-xs ${hoverBg} transition-colors`}
                          >
                            <MessageSquare className="w-3.5 h-3.5 text-gray-400 flex-shrink-0 mt-0.5" strokeWidth={2} />
                            <div className="flex-1 text-left min-w-0">
                              <p className={`truncate ${textSecondary}`}>{chat.title}</p>
                              <p className={`text-[10px] ${textTertiary}`}>{chat.timestamp}</p>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content - 80% width */}
      <div className="flex-1">
        <ProfessionalProjectView
          project={activeProject}
          isDarkMode={isDarkMode}
        />
      </div>
    </div>
  );
}
