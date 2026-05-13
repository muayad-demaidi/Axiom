import { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, Loader2 } from 'lucide-react';
import Papa from 'papaparse';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface UploadedFile {
  id: string;
  name: string;
  size: string;
  type: string;
  file: File;
  parsedData?: any[];
}

interface ChatInterfaceProps {
  files: UploadedFile[];
}

export function ChatInterface({ files }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
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
        content: `Hi! I've detected ${files.length} file${files.length > 1 ? 's' : ''} in your project. I can help you analyze your data. Try asking me questions like:\n\n• "What are the main trends in this data?"\n• "Show me summary statistics"\n• "What insights can you find?"\n• "Create a visualization of the key metrics"\n\nWhat would you like to explore?`,
        timestamp: new Date()
      };
      setMessages([welcomeMessage]);
    }
  }, [files]);

  const generateMockInsight = async (query: string, fileData: UploadedFile[]): Promise<string> => {
    // Parse CSV files if not already parsed
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
        return `Based on analyzing **${csvFiles[0].name}**:\n\n📊 **Dataset Overview**\n• Total rows: ${rowCount}\n• Columns: ${columns.length} (${columns.slice(0, 5).join(', ')}${columns.length > 5 ? '...' : ''})\n\n🔍 **Quick Insights**\n• The dataset appears to be well-structured with ${rowCount} records\n• Key fields include: ${columns.slice(0, 3).join(', ')}\n\nConnect your AI API to get deeper analysis, trends, and predictions!`;
      }

      if (lowerQuery.includes('trend') || lowerQuery.includes('pattern')) {
        return `Looking at patterns in **${csvFiles[0].name}**:\n\n📈 **Trend Analysis**\n• Dataset contains ${rowCount} data points across ${columns.length} dimensions\n• Main variables: ${columns.slice(0, 4).join(', ')}\n\nTo get detailed trend analysis, correlation matrices, and predictive insights, connect your AI API key. I'll be able to:\n• Identify temporal patterns\n• Detect anomalies\n• Generate forecasts\n• Create visualizations`;
      }

      if (lowerQuery.includes('column') || lowerQuery.includes('field')) {
        return `**Available Columns in ${csvFiles[0].name}:**\n\n${columns.map((col, i) => `${i + 1}. **${col}**`).join('\n')}\n\nTotal: ${columns.length} columns across ${rowCount} rows\n\nAsk me about specific columns or relationships between them once you connect your AI API!`;
      }

      return `I can see you have **${csvFiles[0].name}** with ${rowCount} rows and ${columns.length} columns.\n\n**Available data fields:**\n${columns.slice(0, 6).map(col => `• ${col}`).join('\n')}\n\nTo provide detailed analysis, insights, and answer your specific question about "${query}", please connect your AI API key (OpenAI or Anthropic) in the Make settings. This will enable:\n\n✨ Natural language queries\n📊 Statistical analysis\n📈 Trend detection\n🎯 Predictive insights\n📉 Data visualizations`;
    }

    return `I'm ready to analyze your data! However, to provide intelligent responses to "${query}", you need to:\n\n1. **Connect Supabase** from the Make settings page\n2. **Add your AI API key** (OpenAI or Anthropic) in Supabase settings\n\nOnce connected, I'll be able to:\n• Answer complex questions about your data\n• Generate insights and trends\n• Create summaries and reports\n• Suggest visualizations\n• Detect patterns and anomalies`;
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

    // Simulate AI processing
    setTimeout(async () => {
      const insight = await generateMockInsight(inputMessage, files);

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
    "What are the main trends in this data?",
    "Show me summary statistics",
    "What columns are available?",
    "Give me an overview of the dataset"
  ];

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Chat Header */}
      <div className="bg-white border-b px-6 py-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-500 rounded-lg flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="font-semibold">AI Data Analyst</h2>
            <p className="text-xs text-gray-500">Ask me anything about your data</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && files.length === 0 && (
          <div className="text-center py-12">
            <div className="w-16 h-16 bg-gradient-to-br from-indigo-100 to-purple-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <Sparkles className="w-8 h-8 text-indigo-600" />
            </div>
            <h3 className="font-semibold text-lg mb-2">Upload files to start analyzing</h3>
            <p className="text-gray-600 text-sm">Upload CSV, Excel, or JSON files and I'll help you explore your data</p>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-2xl px-4 py-3 rounded-2xl ${
                message.role === 'user'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white border border-gray-200 shadow-sm'
              }`}
            >
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
              <p className={`text-xs mt-2 ${message.role === 'user' ? 'text-indigo-200' : 'text-gray-400'}`}>
                {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 shadow-sm px-4 py-3 rounded-2xl flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
              <p className="text-sm text-gray-600">Analyzing...</p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Example Queries */}
      {messages.length <= 1 && files.length > 0 && (
        <div className="px-6 pb-3">
          <p className="text-xs text-gray-500 mb-2">Try asking:</p>
          <div className="flex flex-wrap gap-2">
            {exampleQueries.map((query, index) => (
              <button
                key={index}
                onClick={() => setInputMessage(query)}
                className="px-3 py-1.5 bg-white border border-gray-200 rounded-full text-xs hover:border-indigo-300 hover:bg-indigo-50 transition-colors"
              >
                {query}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="bg-white border-t p-4">
        <div className="flex gap-3">
          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
            placeholder={files.length > 0 ? "Ask anything about your data..." : "Upload files first..."}
            disabled={files.length === 0}
            className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none disabled:bg-gray-100 disabled:cursor-not-allowed"
          />
          <button
            onClick={handleSendMessage}
            disabled={!inputMessage.trim() || files.length === 0}
            className="px-6 py-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
