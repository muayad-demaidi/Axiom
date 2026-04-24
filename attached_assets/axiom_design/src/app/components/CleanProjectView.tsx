import { useState, useRef, useEffect } from 'react';
import { ArrowLeft, Upload, FileText, FileSpreadsheet, File, X, Send, Sparkles, BarChart2, TrendingUp, Users, MessageSquare } from 'lucide-react';
import Papa from 'papaparse';

interface Project {
  id: string;
  name: string;
  description: string;
  fileCount: number;
  createdAt: string;
  lastModified: string;
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

export function CleanProjectView({ project, onBack }: { project: Project; onBack: () => void }) {
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
        content: `I've loaded ${files.length} file${files.length > 1 ? 's' : ''} into your workspace. You can ask me questions about your data, request analysis, or explore trends. What would you like to know?`,
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
      return <FileSpreadsheet className="w-4 h-4 text-green-600" strokeWidth={2} />;
    }
    if (type === 'pdf') {
      return <FileText className="w-4 h-4 text-red-600" strokeWidth={2} />;
    }
    if (type === 'json') {
      return <File className="w-4 h-4 text-blue-600" strokeWidth={2} />;
    }
    return <File className="w-4 h-4 text-gray-600" strokeWidth={2} />;
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

      if (lowerQuery.includes('summary') || lowerQuery.includes('overview')) {
        return `I've analyzed ${csvFiles[0].name}:\n\n• Total records: ${rowCount.toLocaleString()}\n• Columns: ${columns.length} (${columns.slice(0, 4).join(', ')}${columns.length > 4 ? '...' : ''})\n\nThe dataset appears well-structured. To provide deeper insights like trends, correlations, and predictions, connect your AI API (OpenAI or Anthropic) in the settings.`;
      }

      if (lowerQuery.includes('trend') || lowerQuery.includes('pattern')) {
        return `Looking at ${csvFiles[0].name}:\n\n• Dataset size: ${rowCount.toLocaleString()} rows\n• Dimensions: ${columns.length} columns\n• Key fields: ${columns.slice(0, 3).join(', ')}\n\nTo analyze trends and patterns in detail, you'll need to connect an AI service. This will enable time-series analysis, correlation detection, and forecasting.`;
      }

      if (lowerQuery.includes('column') || lowerQuery.includes('field')) {
        return `Columns in ${csvFiles[0].name}:\n\n${columns.map((col, i) => `${i + 1}. ${col}`).join('\n')}\n\nTotal: ${columns.length} columns across ${rowCount.toLocaleString()} rows.`;
      }

      return `I can see ${csvFiles[0].name} has ${rowCount.toLocaleString()} rows and ${columns.length} columns.\n\nKey fields: ${columns.slice(0, 5).join(', ')}\n\nTo answer "${query}" in detail, connect your AI API in settings. This enables natural language analysis, automated insights, and visualizations.`;
    }

    return `To analyze your data and answer "${query}", please:\n\n1. Upload CSV, Excel, or JSON files\n2. Connect an AI service (OpenAI or Anthropic) in settings\n\nThis will enable conversational analysis, insight generation, and trend detection.`;
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
    }, 1000);
  };

  return (
    <div className="h-screen flex flex-col bg-[#fafaf9]">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="px-6 py-4 flex items-center gap-4">
          <button
            onClick={onBack}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-gray-600" strokeWidth={2} />
          </button>
          <div className="flex-1">
            <h1 className="font-semibold text-gray-900">{project.name}</h1>
            <p className="text-sm text-gray-600">{project.description}</p>
          </div>
          <div className="text-sm text-gray-500">
            {files.length} {files.length === 1 ? 'file' : 'files'}
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-80 bg-white border-r border-gray-200 flex flex-col">
          <div className="p-6 flex-1 overflow-y-auto">
            {/* Upload Area */}
            {files.length === 0 ? (
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
                  isDragging
                    ? 'border-gray-400 bg-gray-50'
                    : 'border-gray-300 hover:border-gray-400'
                }`}
              >
                <div className="flex flex-col items-center gap-3">
                  <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center">
                    <Upload className="w-6 h-6 text-gray-500" strokeWidth={2} />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 mb-1">
                      {isDragging ? 'Drop files here' : 'Upload files'}
                    </p>
                    <p className="text-sm text-gray-500">or drag and drop</p>
                  </div>
                  <label className="px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 transition-colors cursor-pointer">
                    Choose files
                    <input
                      type="file"
                      multiple
                      onChange={(e) => e.target.files && handleFilesUpload(e.target.files)}
                      className="hidden"
                      accept=".csv,.xlsx,.xls,.json,.txt"
                    />
                  </label>
                  <p className="text-xs text-gray-500">CSV, Excel, JSON, TXT</p>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-900">Files</h3>
                  <label className="px-3 py-1.5 border border-gray-300 text-gray-700 text-xs font-medium rounded-lg hover:bg-gray-50 transition-colors cursor-pointer">
                    Add files
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
                      className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors group"
                    >
                      {getFileIcon(file.type)}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">{file.name}</p>
                        <p className="text-xs text-gray-500">{file.size}</p>
                      </div>
                      <button
                        onClick={() => handleRemoveFile(file.id)}
                        className="opacity-0 group-hover:opacity-100 p-1 hover:bg-gray-200 rounded transition-opacity"
                      >
                        <X className="w-4 h-4 text-gray-500" strokeWidth={2} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Insights Panel */}
            {files.length > 0 && (
              <div className="mt-6 pt-6 border-t border-gray-200">
                <h3 className="text-sm font-semibold text-gray-900 mb-4">Quick insights</h3>
                <div className="space-y-3">
                  {[
                    { icon: BarChart2, label: 'Total files', value: files.length },
                    { icon: TrendingUp, label: 'Status', value: 'Ready' },
                    { icon: Users, label: 'Sources', value: 'Local' }
                  ].map((item, i) => (
                    <div key={i} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                      <div className="w-8 h-8 bg-white rounded-lg flex items-center justify-center">
                        <item.icon className="w-4 h-4 text-gray-600" strokeWidth={2} />
                      </div>
                      <div className="flex-1">
                        <p className="text-xs text-gray-600">{item.label}</p>
                        <p className="text-sm font-semibold text-gray-900">{item.value}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Chat Area */}
        <div className="flex-1 flex flex-col bg-white">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.length === 0 && files.length === 0 && (
                <div className="text-center py-20">
                  <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <MessageSquare className="w-6 h-6 text-gray-400" strokeWidth={2} />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">Start analyzing</h3>
                  <p className="text-gray-600">Upload files to begin asking questions about your data</p>
                </div>
              )}

              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {message.role === 'assistant' && (
                    <div className="w-8 h-8 bg-gray-900 rounded-lg flex items-center justify-center mr-3 flex-shrink-0">
                      <Sparkles className="w-4 h-4 text-white" strokeWidth={2} />
                    </div>
                  )}
                  <div
                    className={`max-w-2xl ${
                      message.role === 'user'
                        ? 'bg-gray-900 text-white px-4 py-2.5 rounded-2xl'
                        : 'text-gray-900'
                    }`}
                  >
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
                  </div>
                </div>
              ))}

              {isTyping && (
                <div className="flex justify-start">
                  <div className="w-8 h-8 bg-gray-900 rounded-lg flex items-center justify-center mr-3">
                    <Sparkles className="w-4 h-4 text-white" strokeWidth={2} />
                  </div>
                  <div className="flex items-center gap-1 px-4 py-3">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input */}
          <div className="border-t border-gray-200 p-4 bg-white">
            <div className="max-w-3xl mx-auto">
              <div className="flex gap-3">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
                  placeholder={files.length > 0 ? "Ask a question about your data..." : "Upload files to get started"}
                  disabled={files.length === 0}
                  className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-gray-900 focus:border-transparent outline-none text-gray-900 placeholder-gray-400 disabled:bg-gray-50 disabled:cursor-not-allowed"
                />
                <button
                  onClick={handleSendMessage}
                  disabled={!inputMessage.trim() || files.length === 0}
                  className="px-4 py-3 bg-gray-900 text-white rounded-xl hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send className="w-5 h-5" strokeWidth={2} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
