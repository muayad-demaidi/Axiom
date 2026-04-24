import { AlertCircle, Database, Sparkles } from 'lucide-react';

export function ConnectionBanner() {
  return (
    <div className="bg-amber-50 border-l-4 border-amber-400 p-4 mb-6 rounded-lg">
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
        <div className="flex-1">
          <h3 className="font-semibold text-amber-900 mb-1">Connect to Enable Full Functionality</h3>
          <p className="text-sm text-amber-800 mb-3">
            To store projects, process files, and enable AI-powered analysis, you need to:
          </p>
          <div className="space-y-2 text-sm text-amber-800">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4" />
              <span><strong>Connect Supabase</strong> from the Make settings page for data storage</span>
            </div>
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4" />
              <span><strong>Add your AI API key</strong> (OpenAI or Anthropic) in Supabase settings</span>
            </div>
          </div>
          <p className="text-xs text-amber-700 mt-3">
            Note: Make is designed for prototyping and demos, not for collecting PII or securing highly sensitive data.
          </p>
        </div>
      </div>
    </div>
  );
}
