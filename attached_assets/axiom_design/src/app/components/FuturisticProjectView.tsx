import { useState, useRef, useEffect } from 'react';
import { ArrowLeft, Brain, Upload, FileText, FileSpreadsheet, File, Trash2, Sparkles, Send, Zap, TrendingUp, Database, Activity, Layers } from 'lucide-react';
import Papa from 'papaparse';

interface Project {
  id: string;
  name: string;
  description: string;
  fileCount: number;
  createdAt: string;
  status: 'active' | 'processing' | 'completed';
  insights: number;
}

interface UploadedFile {
  id: string;
  name: string;
  size: string;
  type: string;
  file: File;
  parsedData?: any[];
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export function FuturisticProjectView({ project, onBack }: { project: Project; onBack: () => void }) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (files.length > 0 && messages.length === 0) {
      const welcomeMessage: ChatMessage = {
        id: '1',
        role: 'assistant',
        content: `🧠 **Neural Analysis Initialized**\n\nI've detected ${files.length} dataset${files.length > 1 ? 's' : ''} in your workspace. My neural networks are ready to analyze.\n\n**Quick Start:**\n• "What insights can you find?"\n• "Show me data patterns"\n• "Summarize key metrics"\n• "Create a trend analysis"\n\nWhat would you like to explore first?`,
        timestamp: new Date()
      };
      setMessages([welcomeMessage]);
    }
  }, [files]);

  const handleFilesUpload = async (fileList: FileList) => {
    const newFiles: UploadedFile[] = Array.from(fileList).map((file) => ({
      id: Date.now().toString() + Math.random(),
      name: file.name,
      size: formatFileSize(file.size),
      type: file.name.split('.').pop()?.toLowerCase() || 'file',
      file: file
    }));

    setFiles([...files, ...newFiles]);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const handleRemoveFile = (fileId: string) => {
    setFiles(files.filter(f => f.id !== fileId));
  };

  const getFileIcon = (type: string) => {
    if (type === 'csv' || type === 'xlsx' || type === 'xls') {
      return <FileSpreadsheet className="w-5 h-5 text-green-400" />;
    }
    if (type === 'pdf') {
      return <FileText className="w-5 h-5 text-red-400" />;
    }
    if (type === 'json') {
      return <File className="w-5 h-5 text-blue-400" />;
    }
    return <File className="w-5 h-5 text-gray-400" />;
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      await handleFilesUpload(e.dataTransfer.files);
    }
  };

  const generateInsight = async (query: string, fileData: UploadedFile[]): Promise<string> => {
    const parsedFiles = await Promise.all(
      fileData.map(async (file) => {
        if (file.parsedData) return file;

        if (file.type === 'csv') {
          return new Promise<UploadedFile>((resolve) => {
            Papa.parse(file.file, {
              header: true,
              complete: (results) => {
                resolve({ ...file, parsedData: results.data });
              }
            });
          });
        }
        return file;
      })
    );

    const csvFiles = parsedFiles.filter(f => f.parsedData);

    if (csvFiles.length > 0 && csvFiles[0].parsedData) {
      const data = csvFiles[0].parsedData;
      const columns = Object.keys(data[0] || {});
      const rowCount = data.length;

      const lowerQuery = query.toLowerCase();

      if (lowerQuery.includes('summary') || lowerQuery.includes('overview') || lowerQuery.includes('insight')) {
        return `🔍 **Neural Analysis Complete**\n\n**Dataset:** ${csvFiles[0].name}\n\n📊 **Structure**\n• Rows: ${rowCount.toLocaleString()}\n• Dimensions: ${columns.length}\n• Key Fields: ${columns.slice(0, 4).join(', ')}${columns.length > 4 ? '...' : ''}\n\n🎯 **AI Insights**\n• Dataset is well-structured for analysis\n• ${columns.length} dimensional feature space detected\n• Ready for pattern recognition & forecasting\n\n💡 **Next Steps**\nConnect your AI API (OpenAI/Anthropic) for:\n• Predictive modeling\n• Anomaly detection  \n• Automated insights\n• Natural language queries`;
      }

      if (lowerQuery.includes('trend') || lowerQuery.includes('pattern')) {
        return `📈 **Trend Analysis Initiated**\n\n**Analyzing:** ${csvFiles[0].name}\n\n🔬 **Pattern Detection**\n• ${rowCount.toLocaleString()} data points scanned\n• ${columns.length} feature dimensions analyzed\n• Temporal patterns: Pending AI connection\n• Correlation matrix: Pending AI connection\n\n⚡ **Enable Full Analysis**\nTo unlock advanced pattern recognition:\n1. Connect Supabase (Make settings)\n2. Add AI API key (OpenAI/Anthropic)\n\nYou'll get:\n• Time-series forecasting\n• Correlation heatmaps\n• Outlier detection\n• Predictive models`;
      }

      if (lowerQuery.includes('column') || lowerQuery.includes('field') || lowerQuery.includes('data')) {
        return `🗂️ **Data Schema Analysis**\n\n**File:** ${csvFiles[0].name}\n\n**Available Dimensions (${columns.length}):**\n${columns.map((col, i) => `${i + 1}. **${col}**`).join('\n')}\n\n**Dataset Size:** ${rowCount.toLocaleString()} records\n\n💬 Try asking:\n• "Analyze correlations between [field1] and [field2]"\n• "What are the key trends in [field]?"\n• "Show me outliers in the dataset"\n\n*Full analysis available with AI API connection*`;
      }

      return `🧠 **Processing Query:** "${query}"\n\n**Current Dataset:** ${csvFiles[0].name}\n• Records: ${rowCount.toLocaleString()}\n• Features: ${columns.slice(0, 5).join(', ')}${columns.length > 5 ? '...' : ''}\n\n⚡ **To Answer This Query**\n\nConnect AI capabilities:\n1. **Supabase** → Data persistence\n2. **API Key** → Neural processing\n\nThis unlocks:\n✓ Natural language analysis\n✓ Smart insights generation\n✓ Predictive modeling\n✓ Visual analytics\n\n*Configure in Make settings → Supabase*`;
    }

    return `🚀 **AI Assistant Ready**\n\nTo analyze "${query}", I need:\n\n1️⃣ **Data Connection**\n→ Upload CSV/Excel files\n\n2️⃣ **Neural Backend**\n→ Connect Supabase (Make settings)\n→ Add AI API key (OpenAI/Anthropic)\n\n**What You'll Get:**\n• Conversational data analysis\n• Automated insight generation\n• Pattern & trend detection\n• Predictive analytics\n• Visual dashboards\n\nReady to unlock full AI power?`;
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

    setTimeout(async () => {
      const insight = await generateInsight(inputMessage, files);

      const aiResponse: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: insight,
        timestamp: new Date()
      };

      setMessages(prev => [...prev, aiResponse]);
      setIsTyping(false);
    }, 1500);
  };

  const exampleQueries = [
    "What insights can you find?",
    "Show me data patterns",
    "Analyze key trends",
    "Summarize the dataset"
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white relative overflow-hidden">
      {/* Animated Background */}
      <div className="fixed inset-0 gradient-mesh opacity-30" />
      <div className="fixed inset-0 neural-grid opacity-10" />

      {/* Content */}
      <div className="relative z-10 h-screen flex flex-col">
        {/* Header */}
        <header className="glass-panel-strong border-b border-white/10">
          <div className="px-8 py-4 flex items-center gap-4">
            <button
              onClick={onBack}
              className="p-2.5 glass-panel rounded-xl hover:bg-white/10 transition-all border border-white/10"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-1">
                <h1 className="text-xl font-bold">{project.name}</h1>
                <div className="w-2 h-2 bg-cyan-400 rounded-full glow-pulse" />
              </div>
              <p className="text-sm text-gray-400">{project.description}</p>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-sm text-gray-400">Neural Status</div>
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-green-400" />
                  <span className="text-sm font-medium text-green-400">Active</span>
                </div>
              </div>
            </div>
          </div>
        </header>

        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar */}
          <div className="w-96 glass-panel-strong border-r border-white/10 flex flex-col">
            <div className="p-6 space-y-6 overflow-y-auto flex-1">
              {/* Upload Zone */}
              {files.length === 0 ? (
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`border-2 border-dashed rounded-2xl p-8 text-center transition-all ${
                    isDragging
                      ? 'border-purple-500 bg-purple-500/10 neon-glow-purple'
                      : 'border-white/20 hover:border-purple-500/50 glass-panel'
                  }`}
                >
                  <div className="flex flex-col items-center gap-4">
                    <div className={`w-16 h-16 rounded-2xl flex items-center justify-center transition-all ${
                      isDragging ? 'bg-purple-500/20 neon-glow-purple' : 'glass-panel'
                    }`}>
                      <Upload className="w-8 h-8 text-purple-400" />
                    </div>
                    <div>
                      <p className="font-medium mb-1">
                        {isDragging ? 'Release to upload' : 'Drop files here'}
                      </p>
                      <p className="text-sm text-gray-400">or</p>
                    </div>
                    <label className="px-5 py-2.5 bg-gradient-to-r from-purple-600 to-blue-600 rounded-xl hover:shadow-lg hover:shadow-purple-500/50 transition-all cursor-pointer font-medium neon-glow-purple">
                      Browse Files
                      <input
                        type="file"
                        multiple
                        onChange={(e) => e.target.files && handleFilesUpload(e.target.files)}
                        className="hidden"
                        accept=".csv,.xlsx,.xls,.json,.txt"
                      />
                    </label>
                    <p className="text-xs text-gray-500">
                      CSV, Excel, JSON, TXT
                    </p>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="font-semibold flex items-center gap-2">
                        <Database className="w-4 h-4 text-purple-400" />
                        Data Sources
                      </h3>
                      <p className="text-xs text-gray-400">{files.length} files loaded</p>
                    </div>
                    <label className="px-3 py-1.5 bg-purple-600/20 border border-purple-500/30 text-purple-300 text-sm rounded-lg hover:bg-purple-600/30 transition-all cursor-pointer">
                      + Add
                      <input
                        type="file"
                        multiple
                        onChange={(e) => e.target.files && handleFilesUpload(e.target.files)}
                        className="hidden"
                        accept=".csv,.xlsx,.xls,.json,.txt"
                      />
                    </label>
                  </div>
                  <div className="space-y-2">
                    {files.map((file) => (
                      <div
                        key={file.id}
                        className="glass-panel rounded-xl p-4 hover:bg-white/10 transition-all group border border-white/5"
                      >
                        <div className="flex items-center gap-3">
                          {getFileIcon(file.type)}
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-sm truncate">{file.name}</p>
                            <p className="text-xs text-gray-400">{file.size}</p>
                          </div>
                          <button
                            onClick={() => handleRemoveFile(file.id)}
                            className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-500/20 rounded-lg transition-all"
                          >
                            <Trash2 className="w-4 h-4 text-red-400" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Stats */}
              {files.length > 0 && (
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: 'Files', value: files.length, icon: Layers },
                    { label: 'Insights', value: project.insights, icon: Brain }
                  ].map((stat, i) => (
                    <div key={i} className="glass-panel rounded-xl p-4 border border-white/5">
                      <stat.icon className="w-5 h-5 text-purple-400 mb-2" />
                      <div className="text-2xl font-bold gradient-text">{stat.value}</div>
                      <div className="text-xs text-gray-400">{stat.label}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Chat Area */}
          <div className="flex-1 flex flex-col">
            {/* Chat Header */}
            <div className="glass-panel border-b border-white/10 px-8 py-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-blue-500 rounded-xl flex items-center justify-center neon-glow-purple">
                  <Brain className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h2 className="font-semibold">Neural Assistant</h2>
                  <p className="text-xs text-gray-400">AI-powered data analysis</p>
                </div>
                <div className="ml-auto px-4 py-1.5 glass-panel rounded-full text-xs font-medium border border-purple-500/30 text-purple-300">
                  Preview Mode
                </div>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-8 space-y-6">
              {messages.length === 0 && files.length === 0 && (
                <div className="text-center py-20">
                  <div className="w-20 h-20 bg-gradient-to-br from-purple-500/20 to-blue-500/20 rounded-3xl flex items-center justify-center mx-auto mb-6 glass-panel neon-glow-purple float-animation">
                    <Brain className="w-10 h-10 text-purple-300" />
                  </div>
                  <h3 className="text-2xl font-bold mb-2 gradient-text">Ready to Analyze</h3>
                  <p className="text-gray-400">Upload data to activate neural processing</p>
                </div>
              )}

              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-2xl px-6 py-4 rounded-2xl ${
                      message.role === 'user'
                        ? 'bg-gradient-to-r from-purple-600 to-blue-600 neon-glow-purple'
                        : 'glass-panel border border-white/10'
                    }`}
                  >
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
                    <p className={`text-xs mt-3 ${message.role === 'user' ? 'text-purple-200' : 'text-gray-500'}`}>
                      {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                </div>
              ))}

              {isTyping && (
                <div className="flex justify-start">
                  <div className="glass-panel border border-white/10 px-6 py-4 rounded-2xl flex items-center gap-3">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                      <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                    </div>
                    <p className="text-sm text-gray-400">Neural processing...</p>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Example Queries */}
            {messages.length <= 1 && files.length > 0 && (
              <div className="px-8 pb-4">
                <p className="text-xs text-gray-500 mb-3">Try asking:</p>
                <div className="flex flex-wrap gap-2">
                  {exampleQueries.map((query, index) => (
                    <button
                      key={index}
                      onClick={() => setInputMessage(query)}
                      className="px-4 py-2 glass-panel border border-white/10 rounded-xl text-sm hover:border-purple-500/50 hover:bg-white/5 transition-all"
                    >
                      {query}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Input */}
            <div className="glass-panel border-t border-white/10 p-6">
              <div className="flex gap-3">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
                  placeholder={files.length > 0 ? "Ask anything about your data..." : "Upload files to start..."}
                  disabled={files.length === 0}
                  className="flex-1 px-6 py-4 glass-panel border border-white/10 rounded-2xl focus:ring-2 focus:ring-purple-500 focus:border-transparent outline-none text-white placeholder-gray-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                />
                <button
                  onClick={handleSendMessage}
                  disabled={!inputMessage.trim() || files.length === 0}
                  className="px-6 py-4 bg-gradient-to-r from-purple-600 to-blue-600 rounded-2xl hover:shadow-lg hover:shadow-purple-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 neon-glow-purple group"
                >
                  <Send className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
