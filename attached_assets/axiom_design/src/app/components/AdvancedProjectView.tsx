import { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, Upload, FileText, Database, TrendingUp, BarChart3, Zap, Activity, Brain } from 'lucide-react';
import Papa from 'papaparse';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';

interface Project {
  id: string;
  name: string;
  description: string;
  datasets: number;
  lastActive: string;
  color: string;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  hasChart?: boolean;
  chartData?: any[];
  chartType?: 'line' | 'bar' | 'area';
}

interface DataAsset {
  id: string;
  name: string;
  type: 'csv' | 'sql' | 'json';
  rows: number;
  size: string;
}

export function AdvancedProjectView({ project }: { project: Project }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'assistant',
      content: `Welcome to **${project.name}**. I've loaded your workspace context with ${project.datasets} datasets. What would you like to analyze?`,
      timestamp: new Date(),
      hasChart: false
    }
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [dataAssets] = useState<DataAsset[]>([
    { id: '1', name: 'sales_data.csv', type: 'csv', rows: 15420, size: '2.3 MB' },
    { id: '2', name: 'customer_metrics.csv', type: 'csv', rows: 8934, size: '1.1 MB' },
    { id: '3', name: 'market_trends.sql', type: 'sql', rows: 23451, size: '4.2 MB' }
  ]);

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
        content: `Welcome to **${project.name}**. I've loaded your workspace context with ${project.datasets} datasets. What would you like to analyze?`,
        timestamp: new Date(),
        hasChart: false
      }
    ]);
  }, [project.id]);

  const generateMockChartData = () => {
    return Array.from({ length: 12 }, (_, i) => ({
      month: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][i],
      value: Math.floor(Math.random() * 5000) + 2000,
      target: Math.floor(Math.random() * 5000) + 2000
    }));
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: inputMessage,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsTyping(true);

    setTimeout(() => {
      const shouldShowChart = inputMessage.toLowerCase().includes('trend') ||
                              inputMessage.toLowerCase().includes('chart') ||
                              inputMessage.toLowerCase().includes('visualize');

      const aiResponse: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: shouldShowChart
          ? `I've analyzed the data from **${dataAssets[0].name}**. Here's a visualization showing the trends over the past 12 months:\n\nKey insights:\n• Peak performance in Q3\n• 23% growth year-over-year\n• Strong upward momentum detected`
          : `Based on the data in **${project.name}**, I've identified several key patterns. The dataset contains ${dataAssets[0].rows.toLocaleString()} records across multiple dimensions.\n\nWould you like me to:\n• Generate visualizations\n• Run statistical analysis\n• Identify anomalies`,
        timestamp: new Date(),
        hasChart: shouldShowChart,
        chartData: shouldShowChart ? generateMockChartData() : undefined,
        chartType: shouldShowChart ? 'area' : undefined
      };

      setMessages(prev => [...prev, aiResponse]);
      setIsTyping(false);
    }, 1500);
  };

  const getAssetIcon = (type: string) => {
    if (type === 'csv') return <FileText className="w-4 h-4 text-[#20FF88]" strokeWidth={2} />;
    if (type === 'sql') return <Database className="w-4 h-4 text-[#3D5AFE]" strokeWidth={2} />;
    return <FileText className="w-4 h-4 text-gray-400" strokeWidth={2} />;
  };

  return (
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <div className="bg-[#1A1A1A]/80 backdrop-blur-[20px] border-b border-white/5 px-8 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div
              className="w-3 h-3 rounded-full animate-pulse"
              style={{
                backgroundColor: project.color,
                boxShadow: `0 0 15px ${project.color}`
              }}
            />
            <div>
              <h2 className="text-lg font-bold">{project.name}</h2>
              <p className="text-sm text-gray-500">{project.description}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="px-4 py-2 bg-white/5 rounded-xl border border-white/5 backdrop-blur-xl">
              <div className="flex items-center gap-2 text-sm">
                <Activity className="w-4 h-4 text-[#20FF88]" strokeWidth={2} />
                <span className="text-gray-400">Active Session</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main Chat */}
        <div className="flex-1 flex flex-col">
          <div className="flex-1 overflow-y-auto p-8">
            <div className="max-w-4xl mx-auto space-y-6">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {message.role === 'assistant' && (
                    <div className="w-10 h-10 bg-gradient-to-br from-[#20FF88] to-[#3D5AFE] rounded-xl flex items-center justify-center mr-4 flex-shrink-0 shadow-lg shadow-[#20FF88]/20">
                      <Brain className="w-5 h-5 text-[#0F0F0F]" strokeWidth={2.5} />
                    </div>
                  )}

                  <div className={`max-w-2xl ${message.role === 'user' ? 'ml-12' : ''}`}>
                    <div
                      className={`${
                        message.role === 'user'
                          ? 'bg-gradient-to-r from-[#3D5AFE] to-[#5B7FFF] text-white px-5 py-3 rounded-2xl shadow-lg shadow-[#3D5AFE]/20'
                          : 'text-gray-200'
                      }`}
                    >
                      <p className="text-sm leading-relaxed whitespace-pre-wrap">
                        {message.content.split('**').map((part, i) =>
                          i % 2 === 1 ? <strong key={i} className="font-bold text-[#20FF88]">{part}</strong> : part
                        )}
                      </p>
                    </div>

                    {message.hasChart && message.chartData && (
                      <div className="mt-4 bg-[#1A1A1A]/80 backdrop-blur-[20px] border border-white/10 rounded-2xl p-6 shadow-xl">
                        <div className="mb-4">
                          <h4 className="text-sm font-semibold text-gray-300 mb-1">Trend Analysis</h4>
                          <p className="text-xs text-gray-500">12-month performance overview</p>
                        </div>
                        <ResponsiveContainer width="100%" height={250}>
                          {message.chartType === 'area' ? (
                            <AreaChart data={message.chartData}>
                              <defs>
                                <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor="#20FF88" stopOpacity={0.3}/>
                                  <stop offset="95%" stopColor="#20FF88" stopOpacity={0}/>
                                </linearGradient>
                                <linearGradient id="colorTarget" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor="#3D5AFE" stopOpacity={0.3}/>
                                  <stop offset="95%" stopColor="#3D5AFE" stopOpacity={0}/>
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                              <XAxis dataKey="month" stroke="#666" style={{ fontSize: '12px' }} />
                              <YAxis stroke="#666" style={{ fontSize: '12px' }} />
                              <Tooltip
                                contentStyle={{
                                  backgroundColor: '#1A1A1A',
                                  border: '1px solid #ffffff20',
                                  borderRadius: '8px',
                                  fontSize: '12px'
                                }}
                              />
                              <Area type="monotone" dataKey="value" stroke="#20FF88" strokeWidth={2} fillOpacity={1} fill="url(#colorValue)" />
                              <Area type="monotone" dataKey="target" stroke="#3D5AFE" strokeWidth={2} fillOpacity={1} fill="url(#colorTarget)" />
                            </AreaChart>
                          ) : (
                            <LineChart data={message.chartData}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                              <XAxis dataKey="month" stroke="#666" style={{ fontSize: '12px' }} />
                              <YAxis stroke="#666" style={{ fontSize: '12px' }} />
                              <Tooltip
                                contentStyle={{
                                  backgroundColor: '#1A1A1A',
                                  border: '1px solid #ffffff20',
                                  borderRadius: '8px'
                                }}
                              />
                              <Line type="monotone" dataKey="value" stroke="#20FF88" strokeWidth={3} dot={{ fill: '#20FF88', r: 4 }} />
                            </LineChart>
                          )}
                        </ResponsiveContainer>
                      </div>
                    )}

                    {message.role === 'assistant' && (
                      <p className="text-xs text-gray-600 mt-2">
                        {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    )}
                  </div>
                </div>
              ))}

              {isTyping && (
                <div className="flex justify-start">
                  <div className="w-10 h-10 bg-gradient-to-br from-[#20FF88] to-[#3D5AFE] rounded-xl flex items-center justify-center mr-4 shadow-lg shadow-[#20FF88]/20">
                    <Brain className="w-5 h-5 text-[#0F0F0F]" strokeWidth={2.5} />
                  </div>
                  <div className="flex items-center gap-2 px-5 py-3">
                    <div className="w-2 h-2 bg-[#20FF88] rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-[#3D5AFE] rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                    <div className="w-2 h-2 bg-[#FF6B9D] rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input Area */}
          <div className="bg-[#1A1A1A]/80 backdrop-blur-[20px] border-t border-white/5 p-6">
            <div className="max-w-4xl mx-auto">
              <div className="bg-[#0F0F0F] border border-white/10 rounded-2xl p-2 shadow-xl">
                <div className="flex gap-3">
                  <input
                    type="text"
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
                    placeholder="Ask anything about your data..."
                    className="flex-1 px-4 py-3 bg-transparent outline-none text-white placeholder-gray-500"
                  />
                  <button
                    onClick={handleSendMessage}
                    disabled={!inputMessage.trim()}
                    className="px-6 py-3 bg-gradient-to-r from-[#20FF88] to-[#3D5AFE] rounded-xl hover:shadow-lg hover:shadow-[#20FF88]/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed font-medium text-[#0F0F0F] flex items-center gap-2"
                  >
                    <Send className="w-5 h-5" strokeWidth={2.5} />
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-4 mt-3 text-xs text-gray-600">
                <div className="flex items-center gap-1">
                  <Sparkles className="w-3 h-3" strokeWidth={2} />
                  <span>AI-powered analysis</span>
                </div>
                <span>•</span>
                <span>{dataAssets.length} datasets loaded</span>
              </div>
            </div>
          </div>
        </div>

        {/* Data Assets Panel */}
        <div className="w-80 bg-[#1A1A1A]/60 backdrop-blur-[20px] border-l border-white/5 p-6 overflow-y-auto">
          <div className="mb-6">
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Data Assets</h3>
            <div className="space-y-2">
              {dataAssets.map((asset) => (
                <div
                  key={asset.id}
                  className="bg-white/5 border border-white/10 rounded-xl p-4 hover:bg-white/10 transition-all backdrop-blur-xl"
                >
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 bg-[#0F0F0F] rounded-lg flex items-center justify-center flex-shrink-0 border border-white/10">
                      {getAssetIcon(asset.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-semibold truncate mb-1">{asset.name}</h4>
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        <span>{asset.rows.toLocaleString()} rows</span>
                        <span>•</span>
                        <span>{asset.size}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Quick Stats */}
          <div>
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Quick Stats</h3>
            <div className="space-y-3">
              {[
                { label: 'Total Records', value: '47.8K', icon: Database, color: '#20FF88' },
                { label: 'Avg Query Time', value: '0.8s', icon: Zap, color: '#3D5AFE' },
                { label: 'Insights Found', value: '23', icon: TrendingUp, color: '#FF6B9D' }
              ].map((stat, i) => (
                <div key={i} className="bg-white/5 border border-white/10 rounded-xl p-4 backdrop-blur-xl">
                  <div className="flex items-center justify-between mb-2">
                    <stat.icon className="w-5 h-5" style={{ color: stat.color }} strokeWidth={2} />
                    <span className="text-2xl font-bold" style={{ color: stat.color }}>{stat.value}</span>
                  </div>
                  <p className="text-xs text-gray-500">{stat.label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
