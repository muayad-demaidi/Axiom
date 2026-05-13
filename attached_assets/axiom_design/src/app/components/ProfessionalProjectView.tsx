import { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, ChevronDown, ChevronUp, Code, Table as TableIcon } from 'lucide-react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

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

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  hasCode?: boolean;
  codeContent?: string;
  hasTable?: boolean;
  tableData?: any;
  hasChart?: boolean;
  chartData?: any[];
  chartType?: 'line' | 'bar';
}

export function ProfessionalProjectView({
  project,
  isDarkMode
}: {
  project: Project;
  isDarkMode: boolean;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'assistant',
      content: `I'm ready to analyze data from **${project.name}**. I have access to ${project.datasets.length} dataset${project.datasets.length > 1 ? 's' : ''}. What would you like to explore?`,
      timestamp: new Date()
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [expandedCode, setExpandedCode] = useState<{ [key: string]: boolean }>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeDataset = project.datasets[0]?.name || 'No data';

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Reset chat when project changes
  useEffect(() => {
    setMessages([
      {
        id: '1',
        role: 'assistant',
        content: `I'm ready to analyze data from **${project.name}**. I have access to ${project.datasets.length} dataset${project.datasets.length > 1 ? 's' : ''}. What would you like to explore?`,
        timestamp: new Date()
      }
    ]);
  }, [project.id]);

  const generateMockData = () => {
    return Array.from({ length: 8 }, (_, i) => ({
      month: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug'][i],
      value: Math.floor(Math.random() * 5000) + 2000,
      target: Math.floor(Math.random() * 5000) + 2000
    }));
  };

  const handleSendMessage = () => {
    if (!inputMessage.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: inputMessage,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    const query = inputMessage.toLowerCase();
    setInputMessage('');

    setTimeout(() => {
      const hasChart = query.includes('trend') || query.includes('chart') || query.includes('visualize');
      const hasCode = query.includes('code') || query.includes('python') || query.includes('script');
      const hasTable = query.includes('table') || query.includes('data') || query.includes('show');

      const aiResponse: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: hasChart
          ? `Based on the analysis of **${activeDataset}**, here are the key trends over the past 8 months:\n\n**Key Findings:**\n• Average monthly value: $3,456\n• Peak performance in June (+23%)\n• Steady growth trajectory observed\n• Year-over-year increase of 18%`
          : hasCode
          ? `Here's the Python code to perform this analysis:\n\nThis script loads the data, performs statistical analysis, and generates insights.`
          : hasTable
          ? `Here's a sample of the data from **${activeDataset}**:`
          : `I've analyzed the data from **${activeDataset}**. The dataset contains 15,420 records with 12 columns. I can help you:\n\n• Generate visualizations\n• Perform statistical analysis\n• Identify patterns and trends\n• Create predictive models\n\nWhat specific analysis would you like me to perform?`,
        timestamp: new Date(),
        hasChart,
        chartData: hasChart ? generateMockData() : undefined,
        chartType: hasChart ? 'line' : undefined,
        hasCode,
        codeContent: hasCode ? `import pandas as pd\nimport numpy as np\n\n# Load the dataset\ndf = pd.read_csv('${activeDataset}')\n\n# Calculate statistics\nmean_value = df['value'].mean()\nstd_dev = df['value'].std()\n\n# Identify trends\ntrend = df.groupby('month')['value'].mean()\n\nprint(f"Average: \${mean_value:.2f}")\nprint(f"Std Dev: \${std_dev:.2f}")` : undefined,
        hasTable,
        tableData: hasTable ? {
          headers: ['Month', 'Revenue', 'Customers', 'Growth'],
          rows: [
            ['January', '$45,230', '1,234', '+12%'],
            ['February', '$52,100', '1,456', '+15%'],
            ['March', '$48,900', '1,389', '+8%'],
            ['April', '$61,340', '1,678', '+18%'],
            ['May', '$58,220', '1,590', '+13%']
          ]
        } : undefined
      };

      setMessages(prev => [...prev, aiResponse]);
    }, 1000);
  };

  const bgColor = isDarkMode ? 'bg-[#111827]' : 'bg-[#FFFAF0]';
  const panelBg = isDarkMode ? 'bg-[#1F2937]' : 'bg-[#FFF8E7]';
  const textPrimary = isDarkMode ? 'text-white' : 'text-gray-900';
  const textSecondary = isDarkMode ? 'text-gray-400' : 'text-gray-700';
  const textTertiary = isDarkMode ? 'text-gray-500' : 'text-gray-600';
  const borderColor = isDarkMode ? 'border-gray-700' : 'border-[#F5E6D3]';
  const codeBg = isDarkMode ? 'bg-[#0D1117]' : 'bg-[#FFF5DC]';
  const hoverBg = isDarkMode ? 'hover:bg-gray-800' : 'hover:bg-[#FFF5DC]';

  return (
    <div className={`h-full flex flex-col ${bgColor}`}>
      {/* Header */}
      <div className={`${panelBg} border-b ${borderColor} px-6 py-4`}>
        <h2 className={`text-lg font-semibold ${textPrimary} mb-1`}>{project.name}</h2>
        <div className="flex items-center gap-2">
          <span className={`text-sm ${textSecondary}`}>Active Data:</span>
          <span className="text-sm font-medium text-[#2563EB]">{activeDataset}</span>
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {messages.map((message) => (
            <div key={message.id}>
              {message.role === 'user' ? (
                <div className="flex justify-end">
                  <div className={`max-w-2xl px-4 py-3 rounded-lg ${panelBg} ${textPrimary}`}>
                    <p className="text-sm">{message.content}</p>
                  </div>
                </div>
              ) : (
                <div className="flex justify-start">
                  <div className="max-w-3xl w-full">
                    <div className={`${textPrimary}`}>
                      <p className="text-sm leading-relaxed mb-4 whitespace-pre-line">
                        {message.content.split('**').map((part, i) =>
                          i % 2 === 1 ? (
                            <strong key={i} className="font-semibold">
                              {part}
                            </strong>
                          ) : (
                            part
                          )
                        )}
                      </p>

                      {/* Code Block */}
                      {message.hasCode && message.codeContent && (
                        <div className={`${panelBg} border ${borderColor} rounded-lg overflow-hidden mb-4`}>
                          <div className={`flex items-center justify-between px-4 py-2 border-b ${borderColor}`}>
                            <div className="flex items-center gap-2">
                              <Code className={`w-4 h-4 ${textSecondary}`} strokeWidth={2} />
                              <span className={`text-xs font-medium ${textSecondary}`}>Python</span>
                            </div>
                            <button
                              onClick={() =>
                                setExpandedCode({
                                  ...expandedCode,
                                  [message.id]: !expandedCode[message.id]
                                })
                              }
                              className={`text-xs ${textSecondary} ${hoverBg} px-2 py-1 rounded flex items-center gap-1`}
                            >
                              {expandedCode[message.id] ? (
                                <>
                                  <ChevronUp className="w-3 h-3" strokeWidth={2} />
                                  Hide Code
                                </>
                              ) : (
                                <>
                                  <ChevronDown className="w-3 h-3" strokeWidth={2} />
                                  View Code
                                </>
                              )}
                            </button>
                          </div>
                          {expandedCode[message.id] && (
                            <div className={`${codeBg} p-4 overflow-x-auto`}>
                              <pre className={`text-xs ${textPrimary} font-mono`}>
                                <code>{message.codeContent}</code>
                              </pre>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Data Table */}
                      {message.hasTable && message.tableData && (
                        <div className={`${panelBg} border ${borderColor} rounded-lg overflow-hidden mb-4`}>
                          <div className={`flex items-center gap-2 px-4 py-2 border-b ${borderColor}`}>
                            <TableIcon className={`w-4 h-4 ${textSecondary}`} strokeWidth={2} />
                            <span className={`text-xs font-medium ${textSecondary}`}>Data Preview</span>
                          </div>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead className={`${isDarkMode ? 'bg-[#0D1117]' : 'bg-gray-50'}`}>
                                <tr>
                                  {message.tableData.headers.map((header: string, i: number) => (
                                    <th
                                      key={i}
                                      className={`px-4 py-3 text-left text-xs font-semibold ${textSecondary} uppercase tracking-wider`}
                                    >
                                      {header}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-gray-700">
                                {message.tableData.rows.map((row: string[], i: number) => (
                                  <tr key={i} className={hoverBg}>
                                    {row.map((cell: string, j: number) => (
                                      <td key={j} className={`px-4 py-3 ${textPrimary}`}>
                                        {cell}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          <div className={`px-4 py-2 border-t ${borderColor} ${textTertiary} text-xs`}>
                            Showing 5 of 15,420 rows
                          </div>
                        </div>
                      )}

                      {/* Chart */}
                      {message.hasChart && message.chartData && (
                        <div className={`${panelBg} border ${borderColor} rounded-lg p-6 mb-4`}>
                          <div className="mb-4">
                            <h4 className={`text-sm font-semibold ${textPrimary} mb-1`}>
                              Trend Analysis
                            </h4>
                            <p className={`text-xs ${textSecondary}`}>8-month performance overview</p>
                          </div>
                          <ResponsiveContainer width="100%" height={280}>
                            <LineChart data={message.chartData}>
                              <CartesianGrid
                                strokeDasharray="3 3"
                                stroke={isDarkMode ? '#374151' : '#E5E7EB'}
                              />
                              <XAxis
                                dataKey="month"
                                stroke={isDarkMode ? '#9CA3AF' : '#6B7280'}
                                style={{ fontSize: '12px' }}
                              />
                              <YAxis
                                stroke={isDarkMode ? '#9CA3AF' : '#6B7280'}
                                style={{ fontSize: '12px' }}
                              />
                              <Tooltip
                                contentStyle={{
                                  backgroundColor: isDarkMode ? '#1F2937' : '#FFFFFF',
                                  border: `1px solid ${isDarkMode ? '#374151' : '#E5E7EB'}`,
                                  borderRadius: '6px',
                                  fontSize: '12px',
                                  color: isDarkMode ? '#FFFFFF' : '#111827'
                                }}
                              />
                              <Line
                                type="monotone"
                                dataKey="value"
                                stroke="#2563EB"
                                strokeWidth={2}
                                dot={{ fill: '#2563EB', r: 4 }}
                              />
                              <Line
                                type="monotone"
                                dataKey="target"
                                stroke="#64748B"
                                strokeWidth={2}
                                strokeDasharray="5 5"
                                dot={{ fill: '#64748B', r: 4 }}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      )}

                      <p className={`text-xs ${textTertiary} mt-2`}>
                        {message.timestamp.toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className={`${panelBg} border-t ${borderColor} px-6 py-4`}>
        <div className="max-w-4xl mx-auto">
          <div className={`flex items-center gap-3 px-4 py-3 border ${borderColor} rounded-lg ${bgColor}`}>
            <button className={`${textSecondary} ${hoverBg} p-1 rounded`}>
              <Paperclip className="w-5 h-5" strokeWidth={2} />
            </button>
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder={`Ask a question about this project's data...`}
              className={`flex-1 bg-transparent outline-none ${textPrimary} placeholder-gray-500 text-sm`}
            />
            <button
              onClick={handleSendMessage}
              disabled={!inputMessage.trim()}
              className="text-[#2563EB] disabled:opacity-40 disabled:cursor-not-allowed p-1 hover:bg-blue-50 dark:hover:bg-blue-950 rounded transition-colors"
            >
              <Send className="w-5 h-5" strokeWidth={2} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
